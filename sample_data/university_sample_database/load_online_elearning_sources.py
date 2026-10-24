"""Load attributed OULAD and OpenLearn materials into Odoo eLearning."""
import csv
import html
import json
import os
import time
import urllib.request
import zipfile
import xmlrpc.client
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(os.path.dirname(BASE), 'oulad')
ZIP_PATH = os.path.join(SOURCE_DIR, 'anonymisedData.zip')
SOURCE_URL = 'https://archive.ics.uci.edu/static/public/349/open%2Buniversity%2Blearning%2Banalytics%2Bdataset.zip'
OULAD_PAGE = 'https://research.stem.open.ac.uk/ouanalyse/dataset/'
OPENLEARN_PAGE = 'https://www.open.edu/openlearn/digital-computing/digital-skills-succeeding-digital-world'
DB_URL = 'http://localhost:8069'
DB = 'openeducat'
LOGIN = 'admin'
PASSWORD = 'admin'
OULAD_PREFIX = '[OULAD] '
OPENLEARN_PREFIX = '[OpenLearn] '


def download_source():
    os.makedirs(SOURCE_DIR, exist_ok=True)
    if os.path.isfile(ZIP_PATH) and zipfile.is_zipfile(ZIP_PATH):
        return
    last_error = None
    for attempt in range(5):
        request = urllib.request.Request(SOURCE_URL, headers={
            'User-Agent': 'Mozilla/5.0 (OpenEduCat sample data loader)', 'Accept': '*/*'})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, open(ZIP_PATH, 'wb') as target:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
            break
        except Exception as error:
            last_error = error
            if os.path.exists(ZIP_PATH):
                os.remove(ZIP_PATH)
            time.sleep(2 + attempt * 2)
    else:
        raise RuntimeError('Unable to download the official OULAD archive') from last_error
    if not zipfile.is_zipfile(ZIP_PATH):
        raise RuntimeError('Downloaded OULAD source did not pass ZIP validation')


def read_csv_from_zip(archive, filename):
    match = next((name for name in archive.namelist() if name.lower().endswith('/' + filename.lower())
                  or name.lower() == filename.lower()), None)
    if not match:
        raise RuntimeError('Source ZIP is missing ' + filename)
    with archive.open(match) as stream:
        return list(csv.DictReader((line.decode('utf-8-sig') for line in stream)))


def activity_summary(archive, vle_rows):
    site_types = {int(row['id_site']): row['activity_type'] for row in vle_rows}
    clicks = defaultdict(Counter)
    learners = defaultdict(set)
    student_vle_name = next((name for name in archive.namelist()
                             if name.lower().endswith('/studentvle.csv')
                             or name.lower() == 'studentvle.csv'), None)
    if not student_vle_name:
        raise RuntimeError('Source ZIP is missing studentVle.csv')
    with archive.open(student_vle_name) as stream:
        reader = csv.DictReader((line.decode('utf-8-sig') for line in stream))
        for row in reader:
            key = (row['code_module'], row['code_presentation'])
            clicks[key][site_types.get(int(row['id_site']), 'other')] += int(row['sum_click'])
            learners[key].add(row['id_student'])
    return clicks, learners


common = xmlrpc.client.ServerProxy(DB_URL + '/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(DB, LOGIN, PASSWORD, {})
if not uid:
    raise SystemExit('Could not authenticate to local OpenEduCat')
models = xmlrpc.client.ServerProxy(DB_URL + '/xmlrpc/2/object', allow_none=True)


def call(model, method, args=None, kwargs=None):
    return models.execute_kw(DB, uid, PASSWORD, model, method, args or [], kwargs or {})


def ensure_channel(name, description, sequence):
    rows = call('slide.channel', 'search_read', [[('name', '=', name)]],
                {'fields': ['id'], 'limit': 1})
    if rows:
        return rows[0]['id']
    return call('slide.channel', 'create', [{
        'name': name,
        'description': description,
        'channel_type': 'training',
        'enroll': 'public',
        'visibility': 'public',
        'sequence': sequence,
        'user_id': uid,
        'is_published': True,
        'website_published': True,
    }])


def ensure_article(channel_id, name, body, sequence, url=None, duration=8):
    prior = call('slide.slide', 'search_read',
        [[('channel_id', '=', channel_id), ('name', '=', name)]],
        {'fields': ['id'], 'limit': 1})
    if prior:
        return prior[0]['id']
    body = body + (
        '<p><strong>Source:</strong> <a href="%s" target="_blank" rel="noreferrer">%s</a></p>'
        % (html.escape(url or OULAD_PAGE, quote=True), html.escape(url or OULAD_PAGE)))
    return call('slide.slide', 'create', [{
        'name': name,
        'channel_id': channel_id,
        'slide_category': 'article',
        'slide_type': 'article',
        'source_type': 'local_file',
        'html_content': '<article>%s</article>' % body,
        'description': body,
        'completion_time': float(duration),
        'sequence': sequence,
        'is_preview': True,
        'is_published': True,
        'website_published': True,
        'user_id': uid,
    }])


download_source()
with zipfile.ZipFile(ZIP_PATH) as archive:
    course_rows = read_csv_from_zip(archive, 'courses.csv')
    assessment_rows = read_csv_from_zip(archive, 'assessments.csv')
    vle_rows = read_csv_from_zip(archive, 'vle.csv')
    clicks, learners = activity_summary(archive, vle_rows)

assessments = defaultdict(list)
for row in assessment_rows:
    assessments[(row['code_module'], row['code_presentation'])].append(row)
vle_types = defaultdict(Counter)
for row in vle_rows:
    key = (row['code_module'], row['code_presentation'])
    vle_types[key][row['activity_type']] += 1

# Create one published course per OULAD module presentation, linked to its SIS course.
sis_courses = call('op.course', 'search_read', [[('name', 'like', 'OULAD %')]],
                   {'fields': ['id', 'name'], 'limit': 100})
sis_by_name = {row['name']: row['id'] for row in sis_courses}
channel_by_key = {}
sis_course_by_key = {}
for sequence, source in enumerate(course_rows, 1):
    key = (source['code_module'], source['code_presentation'])
    title = 'OULAD %s (%s)' % key
    sis_id = sis_by_name.get(title)
    channel_name = OULAD_PREFIX + title
    desc = ('Sample online course presentation from the Open University Learning Analytics Dataset. '
            'The source contains anonymized learner, assessment, and virtual learning environment '
            'activity records. This eLearning course summarizes the data; it is not a copy of the '
            'Open University teaching materials.')
    channel_id = ensure_channel(channel_name, '<p>%s</p>' % desc, sequence + 10)
    channel_by_key[key] = channel_id
    sis_course_by_key[key] = sis_id
    assess = assessments.get(key, [])
    assess_types = Counter(x['assessment_type'] for x in assess)
    type_summary = ', '.join('%s (%s)' % (name, count) for name, count in sorted(assess_types.items())) or 'No assessment rows'
    activity_counts = clicks.get(key, Counter())
    activity_lines = ''.join('<li>%s: %s clicks</li>' % (html.escape(name), format(count, ','))
                             for name, count in activity_counts.most_common(8))
    vle_count = vle_types.get(key, Counter())
    vle_lines = ''.join('<li>%s: %s activities</li>' % (html.escape(name), count)
                        for name, count in vle_count.most_common(8))
    external = '%s#%s-%s' % (OULAD_PAGE, source['code_module'], source['code_presentation'])
    ensure_article(channel_id, OULAD_PREFIX + 'Presentation overview',
        '<p>Module <strong>%s</strong>, presentation <strong>%s</strong>, with a scheduled '
        'length of %s days.</p><p>OULAD is an anonymized learning analytics dataset. '
        'It describes learner registrations and outcomes alongside activity in a virtual '
        'learning environment.</p>' % (html.escape(source['code_module']),
          html.escape(source['code_presentation']), html.escape(source['module_presentation_length'])),
        1, external, 5)
    ensure_article(channel_id, OULAD_PREFIX + 'Assessment profile',
        '<p>This presentation has %s assessment records. Assessment types and counts:</p><ul>%s</ul>'
        % (len(assess), ''.join('<li>%s: %s</li>' % (html.escape(n), c)
                                for n, c in sorted(assess_types.items())) or '<li>None listed</li>'),
        2, external, 5)
    ensure_article(channel_id, OULAD_PREFIX + 'VLE activity profile',
        '<p>The source records %s learner interactions and %s distinct anonymized learners '
        'for this presentation. Activity types represented in the VLE structure:</p><ul>%s</ul>'
        '<p>Recorded clicks by activity type:</p><ul>%s</ul>'
        % (format(sum(activity_counts.values()), ','), len(learners.get(key, set())),
           vle_lines or '<li>No activity type rows</li>', activity_lines or '<li>No click rows</li>'),
        3, external, 10)

# Enroll each existing anonymized SIS learner-course registration in the matching eLearning course.
sis_ids = [sid for sid in sis_course_by_key.values() if sid]
enrollments = call('op.student.course', 'search_read', [[('course_id', 'in', sis_ids)]],
    {'fields': ['student_id', 'course_id', 'state'], 'limit': 50000}) if sis_ids else []
channel_by_sis = {sis_id: channel_by_key[key] for key, sis_id in sis_course_by_key.items() if sis_id}
student_ids = list({row['student_id'][0] for row in enrollments if row.get('student_id')})
student_partners = {}
for offset in range(0, len(student_ids), 1000):
    student_rows = call('op.student', 'search_read',
        [[('id', 'in', student_ids[offset:offset + 1000])]],
        {'fields': ['partner_id'], 'limit': 1000})
    student_partners.update({row['id']: row.get('partner_id') for row in student_rows})
channel_ids = list(channel_by_key.values())
members = call('slide.channel.partner', 'search_read', [[('channel_id', 'in', channel_ids)]],
               {'fields': ['channel_id', 'partner_id'], 'limit': 100000})
member_keys = {(r['channel_id'][0], r['partner_id'][0])
               for r in members if r.get('channel_id') and r.get('partner_id')}
member_vals = []
for row in enrollments:
    if not row.get('student_id') or not row.get('course_id'):
        continue
    partner_id = student_partners.get(row['student_id'][0])
    channel_id = channel_by_sis.get(row['course_id'][0])
    if not partner_id or not channel_id or (channel_id, partner_id[0]) in member_keys:
        continue
    member_vals.append({'channel_id': channel_id, 'partner_id': partner_id[0],
                        'member_status': 'completed' if row.get('state') == 'finished' else 'ongoing'})
    member_keys.add((channel_id, partner_id[0]))
for offset in range(0, len(member_vals), 400):
    call('slide.channel.partner', 'create', [member_vals[offset:offset + 400]])

# OpenLearn content stays canonical on the Open University site. Local lessons are short,
# attributed orientation notes; the full course package could not be retrieved from its endpoint.
openlearn_channel = ensure_channel(
    OPENLEARN_PREFIX + 'Digital skills: succeeding in a digital world',
    '<p>Course by The Open University. Study the original course through the linked OpenLearn pages. '
    'The notes here are brief orientation summaries, not a reproduction of the source lessons.</p>'
    '<p>Attribution: The Open University, <a href="%s">Digital skills: succeeding in a digital world</a>. '
    'OpenLearn materials are for non-commercial use under the applicable Creative Commons terms; '
    'check each course acknowledgement and special restrictions. Third-party media may be excluded.</p>' % OPENLEARN_PAGE,
    1)
openlearn_weeks = [
    ('Week 1: Your digital life', 'Reflect on the role of digital tools in everyday life and identify where digital confidence can improve.', '105152'),
    ('Week 2: Getting up and running', 'Explore digital literacy, finding and evaluating information, communicating, and collaborating online.', '105154'),
    ('Week 3: Making your mark online', 'Consider digital identity, digital footprints, openness, privacy, and responsible participation.', '105156'),
    ('Week 4: Staying safe and legal', 'Review practical online safety, personal data protection, digital well-being, and copyright responsibilities.', '105158'),
    ('Week 5: Critical consumption', 'Practice searching, handling information overload, and judging whether a source deserves trust.', '105160'),
    ('Week 6: Tools for everyday life', 'Compare tools for communicating, creating, collaborating, and managing information or tasks.', '105162'),
    ('Week 7: Reviewing your progress', 'Use examples and reflection to assess progress and identify next steps for developing digital skills.', '105164'),
    ('Week 8: Continuing your digital journey', 'Review learning, plan future skill development, and consider safe and critical use of digital tools.', '105166'),
]
for seq, (title, summary, page_id) in enumerate(openlearn_weeks, 1):
    official_url = 'https://www.open.edu/openlearn/mod/oucontent/view.php?id=' + page_id
    body = ('<p>%s</p><p>This orientation note summarizes the publicly listed week themes. '
            'Read the full lesson, activities, references, and any applicable acknowledgements on OpenLearn.</p>'
            '<p><strong>Attribution:</strong> The Open University, <em>Digital skills: succeeding in a digital world</em>. '
            'Use is subject to the course Creative Commons terms and any special restrictions. '
            'This local page links to the canonical source.</p>') % summary
    ensure_article(openlearn_channel, OPENLEARN_PREFIX + title, body, seq,
                   official_url, 180)

summary = {
    'source': OULAD_PAGE,
    'license': 'CC BY 4.0; attribute the Open University and cite the dataset paper.',
    'presentations': len(course_rows),
    'activity_rows_processed': sum(sum(c.values()) for c in clicks.values()),
    'openlearn_source': OPENLEARN_PAGE,
    'openlearn_license_note': 'Non-commercial Creative Commons terms; check acknowledgements and special restrictions.',
}
with open(os.path.join(SOURCE_DIR, 'import_summary.json'), 'w', encoding='utf-8') as f:
    json.dump(summary, f, indent=2)
print('OULAD presentations loaded:', len(course_rows))
print('OULAD VLE interaction events summarized:', format(summary['activity_rows_processed'], ','))
print('OULAD SIS enrollment rows linked:', len(enrollments))
print('OpenLearn course pages loaded:', len(openlearn_weeks))
print('OULAD eLearning channels:', call('slide.channel', 'search_count',
    [[('name', 'like', OULAD_PREFIX + '%')]]))
print('OpenLearn eLearning lessons:', call('slide.slide', 'search_count',
    [[('channel_id', '=', openlearn_channel)]]))
