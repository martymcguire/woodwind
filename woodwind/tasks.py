from woodwind.models import Feed, Entry
from config import Config
from contextlib import contextmanager
import celery
import celery.utils.log
import feedparser
import mf2py
import mf2util
import time
import urllib.parse
import datetime
import sqlalchemy
import sqlalchemy.orm

UPDATE_INTERVAL = datetime.timedelta(hours=1)

app = celery.Celery('woodwind')
app.config_from_object('celeryconfig')

logger = celery.utils.log.get_task_logger(__name__)
engine = sqlalchemy.create_engine(Config.SQLALCHEMY_DATABASE_URI)
Session = sqlalchemy.orm.sessionmaker(bind=engine)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


@app.task
def tick():
    with session_scope() as session:
        now = datetime.datetime.utcnow()
        logger.debug('Tick {}'.format(now))
        for feed in session.query(Feed).all():
            logger.debug('Feed {} last checked {}'.format(
                feed, feed.last_checked))
            if (not feed.last_checked
                    or now - feed.last_checked > UPDATE_INTERVAL):
                update_feed.delay(feed.id)


@app.task
def update_feed(feed_id):
    with session_scope() as session:
        feed = session.query(Feed).get(feed_id)
        logger.info('Updating {}'.format(feed))
        new_entries = process_feed_for_new_entries(session, feed)
        for entry in new_entries:
            logger.debug('Got new entry: {}'.format(entry))


def process_feed_for_new_entries(session, feed):
    result = None
    try:
        if feed.type == 'xml':
            result = list(process_xml_feed_for_new_entries(session, feed))
        elif feed.type == 'html':
            result = list(process_html_feed_for_new_entries(session, feed))
    finally:
        now = datetime.datetime.utcnow()
        feed.last_checked = now
        if result:
            feed.last_updated = now
        session.commit()
    return result



def process_xml_feed_for_new_entries(session, feed):
    logger.debug('fetching xml feed: %s', feed)

    now = datetime.datetime.utcnow()
    parsed = feedparser.parse(feed.feed)

    feed_props = parsed.get('feed', {})
    default_author_url = feed_props.get('author_detail', {}).get('href')
    default_author_name = feed_props.get('author_detail', {}).get('name')
    default_author_photo = feed_props.get('logo')

    all_uids = [e.id or e.link for e in parsed.entries]
    if all_uids:
        preexisting = set(row[0] for row in session.query(Entry.uid)
                          .filter(Entry.uid.in_(all_uids))
                          .filter(Entry.feed == feed))
    else:
        preexisting = set()

    logger.debug('found {} entries'.format(len(parsed.entries)))
    for p_entry in parsed.entries:
        logger.debug('processing entry {}'.format(p_entry))
        permalink = p_entry.link
        uid = p_entry.id or permalink

        if not uid or uid in preexisting:
            continue

        if 'updated_parsed' in p_entry:
            updated = datetime.datetime.fromtimestamp(
                time.mktime(p_entry.updated_parsed)) 
        else:
            updated = None

        if 'published_parsed' in p_entry:
            published = datetime.datetime.fromtimestamp(
                time.mktime(p_entry.published_parsed))
        else:
            published = updated or now

        title = p_entry.get('title')

        content = None
        content_list = p_entry.get('content')
        if content_list:
            content = content_list[0].value
        else:
            content = p_entry.get('summary')

        if title and content:
            title_trimmed = title.rstrip('...').rstrip('…')
            if content.startswith(title_trimmed):
                title = None

        entry = Entry(
            feed=feed,
            published=published,
            updated=updated,
            uid=uid,
            permalink=permalink,
            retrieved=now,
            title=p_entry.get('title'),
            content=content,
            author_name=p_entry.get('author_detail', {}).get('name')
            or default_author_name,
            author_url=p_entry.get('author_detail', {}).get('href')
            or default_author_url,
            author_photo=default_author_photo
            or fallback_photo(feed.origin))

        session.add(entry)
        session.commit()
        yield entry


def process_html_feed_for_new_entries(session, feed):
    logger.debug('fetching html feed: %s', feed)

    now = datetime.datetime.utcnow()
    parsed = mf2util.interpret_feed(
        mf2py.Parser(url=feed.feed).to_dict(), feed.feed)
    hfeed = parsed.get('entries', [])

    for hentry in hfeed:
        permalink = url = hentry.get('url')
        uid = hentry.get('uid') or url
        if not uid:
            continue
        
        entry = session.query(Entry)\
            .filter(Entry.feed == feed)\
            .filter(Entry.uid == uid).first()

        # hentry = mf2util.interpret(mf2py.Parser(url=url).to_dict(), url)
        # permalink = hentry.get('url') or url
        # uid = hentry.get('uid') or uid

        name = hentry.get('name')
        content = hentry.get('content')

        if not entry:
            entry = Entry(feed=feed, uid=uid, retrieved=now)
            session.add(entry)
                    
        entry.published = hentry.get('published') or entry.published or now
        entry.updated = hentry.get('updated') or entry.updated
        entry.permalink = permalink
        if content:
            entry.title = name
            entry.content = content
        else:
            entry.title = None
            entry.content = name
        entry.author_name = hentry.get('author', {}).get('name')
        entry.author_photo = hentry.get('author', {}).get('photo') or fallback_photo(feed.origin)
        entry.author_url = hentry.get('author', {}).get('url')

        session.commit()
        logger.debug('saved entry: %s', entry.permalink)
        yield entry


def fallback_photo(url):
    """Use favatar to find an appropriate photo for any URL"""
    domain = urllib.parse.urlparse(url).netloc
    return 'http://www.google.com/s2/favicons?domain=' + domain