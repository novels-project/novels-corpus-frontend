import collections
import datetime
import json
import os

import bottle
import cherrypy.process.plugins
import requests


NOVELS_API_ADDR = os.environ.get('NOVELS_API_ADDR', None)
PROJECT_DIR = os.path.dirname(__name__)
STATIC_DIR = os.path.join(PROJECT_DIR, 'static')

DEBUG = os.environ.get('DEBUG', False)

works = dict()
works_with_scans = dict()
volumes_by_sha1 = dict()
stats = dict()


if NOVELS_API_ADDR is None:
    raise RuntimeError("Needed API endpoint NOVELS_API_ADDR is missing")

def update_database():
    """Update the in-memory 'database' of novels and volumes"""
    global works, works_with_scans, volumes_by_sha1, stats
    print("Starting database update")
    works_url = NOVELS_API_ADDR + '/work/'
    works_json = requests.get(works_url, verify=False).json()
    # the dictionary key should be an integer but JSON can't represent this
    works_items = [(int(k), v) for k, v in works_json.items()]
    works_items.sort(key=lambda pair: pair[1]['year'])
    works = collections.OrderedDict(works_items)
    works_with_scans = works.copy()
    novels_count = 0
    novels_with_scan_count = 0
    volumes_count = 0
    timestamp_most_recent = datetime.datetime.strptime('1970-1-1', '%Y-%m-%d')
    for key, work in works.items():
        novels_count += 1
        if 'volumes' in work:
            volumes_count += len(work['volumes'])
            novels_with_scan_count += 1
            for vol in work['volumes']:
                # add a reference to the work in each volume record
                vol['work'] = work
                sha1 = vol['sha1']
                if sha1 in volumes_by_sha1:
                    raise ValueError("Encountered duplicate SHA1 {} for volume:\n{}".format(sha1, vol))
                assert sha1 not in volumes_by_sha1
                volumes_by_sha1[sha1] = vol
                timestamp = datetime.datetime.strptime(vol['date_updated'], '%Y-%m-%d')
                timestamp_most_recent = max(timestamp_most_recent, timestamp)
        else:
            del works_with_scans[key]

    stats['date_most_recent_change'] = timestamp_most_recent.strftime('%Y-%m-%d')
    stats['novels_count'] = novels_count
    stats['novels_with_scan_count'] = novels_with_scan_count
    stats['volumes_count'] = volumes_count
    print("Finished database update")


@bottle.route('/')
@bottle.jinja2_view('home')
def home():
    return dict(novels_api_addr=NOVELS_API_ADDR, stats=stats)


@bottle.route('/works')
@bottle.jinja2_view('works')
def work_list():
    return dict(works=works_with_scans.values())


@bottle.route('/volume/<sha1:re:[0-9a-f]+>')
@bottle.jinja2_view('volume_detail')
def volume_detail(sha1):
    volume = volumes_by_sha1[sha1]
    return dict(novels_api_addr=NOVELS_API_ADDR, volume=volume, work=volume['work'])


@bottle.route('/static/<filepath:path>')
def static(filepath):
    return bottle.static_file(filepath, root=STATIC_DIR)


if __name__ == '__main__':
    update_database()
    if DEBUG:
        bottle.run(debug=True, host='0.0.0.0', port=8080)
    else:
        update_runner = cherrypy.process.plugins.Monitor(cherrypy.engine, update_database, frequency=3600 * 24)
        update_runner.subscribe()
        bottle.run(server='cherrypy', host='0.0.0.0', port=8080)
