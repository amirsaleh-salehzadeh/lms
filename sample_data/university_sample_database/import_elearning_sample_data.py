"""Seed local Odoo eLearning channels, lessons, quizzes, and attendees."""
import xmlrpc.client

URL = 'http://localhost:8069'
DB = 'openeducat'
LOGIN = 'admin'
PASSWORD = 'admin'
PREFIX = '[Sample eLearning] '
common = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(DB, LOGIN, PASSWORD, {})
if not uid:
    raise SystemExit('Could not authenticate to local OpenEduCat')
models = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/object', allow_none=True)


def call(model, method, args=None, kwargs=None):
    return models.execute_kw(DB, uid, PASSWORD, model, method, args or [], kwargs or {})


courses = [
    {
        'name': 'Digital Learning Foundations',
        'description': '<p>Sample orientation to online learning, study habits, and responsible use of digital tools.</p>',
        'lessons': [
            ('Welcome to the Learning Platform', '<p>Learn how to navigate a course, find learning materials, and track your progress.</p>'),
            ('Planning a Weekly Study Routine', '<p>Break a large learning goal into short study sessions. Set a calendar reminder and review your notes at the end of each week.</p>'),
            ('Digital Citizenship and Online Safety', '<p>Protect your account, cite sources, communicate respectfully, and check the reliability of online information.</p>'),
        ],
        'quiz': ('Foundations Knowledge Check', [
            ('Which action best supports steady progress in an online course?',
             ['Study regularly and review progress', 'Wait until the final day', 'Skip the course outline'], 0),
            ('What should you do before sharing an online source?',
             ['Check its reliability and cite it', 'Remove the author name', 'Assume every source is accurate'], 0),
        ]),
    },
    {
        'name': 'Introduction to Data Literacy',
        'description': '<p>Sample lessons on reading tables, interpreting charts, and using evidence carefully.</p>',
        'lessons': [
            ('Reading a Data Table', '<p>Start with the title, identify what each row represents, and check the units and date range before comparing values.</p>'),
            ('Choosing and Reading Charts', '<p>Bar charts compare groups, line charts show change over time, and scatter plots show relationships between two measures.</p>'),
            ('Summarising Evidence', '<p>Describe the main pattern, include a useful number, and avoid claiming that a relationship proves a cause.</p>'),
        ],
        'quiz': ('Data Literacy Quiz', [
            ('Which chart is usually useful for showing a measure over time?',
             ['Line chart', 'Floor plan', 'Word cloud'], 0),
            ('A correlation between two measures proves that one caused the other.',
             ['True', 'False'], 1),
        ]),
    },
    {
        'name': 'Academic Writing Essentials',
        'description': '<p>Sample practice in planning, paragraph structure, source use, and revision.</p>',
        'lessons': [
            ('Building a Clear Paragraph', '<p>Use a focused topic sentence, explain the point, support it with evidence, and connect it to the argument.</p>'),
            ('Using Sources and Citations', '<p>Paraphrase in your own words, cite the source, and include enough detail for a reader to find it.</p>'),
            ('Revising a First Draft', '<p>Review the argument and structure first, then improve clarity, grammar, and formatting.</p>'),
        ],
        'quiz': ('Writing Essentials Check', [
            ('What is a useful first step when revising an essay?',
             ['Check the argument and structure', 'Change every font', 'Delete all citations'], 0),
            ('Paraphrased ideas from a source still need citation.',
             ['True', 'False'], 0),
        ]),
    },
    {
        'name': 'Project Management Basics',
        'description': '<p>Sample introduction to project goals, tasks, timelines, risks, and team communication.</p>',
        'lessons': [
            ('Defining a Project Goal', '<p>Write a specific outcome, identify who benefits, and agree how the team will know the work is complete.</p>'),
            ('Tasks, Owners, and Milestones', '<p>Break the work into tasks, assign an owner to each task, and use milestones to check progress.</p>'),
            ('Managing Risks and Changes', '<p>Record likely risks, decide how to respond, and communicate changes that affect scope or timing.</p>'),
        ],
        'quiz': ('Project Management Check', [
            ('Why assign an owner to each task?',
             ['To make responsibility clear', 'To remove the project goal', 'To avoid tracking progress'], 0),
            ('When should a team communicate a change that affects the timeline?',
             ['When it is identified', 'Only after the project ends', 'Never'], 0),
        ]),
    },
]

# Use exact names as stable keys so this script can be rerun safely.
channel_rows = call('slide.channel', 'search_read', [[]],
                    {'fields': ['id', 'name'], 'limit': 1000})
channel_map = {row['name']: row['id'] for row in channel_rows}
for sequence, data in enumerate(courses, 1):
    name = PREFIX + data['name']
    if name not in channel_map:
        channel_id = call('slide.channel', 'create', [{
            'name': name,
            'description': data['description'],
            'channel_type': 'training',
            'enroll': 'public',
            'visibility': 'public',
            'sequence': sequence,
            'user_id': uid,
            'is_published': True,
            'website_published': True,
        }])
        channel_map[name] = channel_id

    channel_id = channel_map[name]
    existing_slides = call('slide.slide', 'search_read',
        [[('channel_id', '=', channel_id)]], {'fields': ['id', 'name'], 'limit': 1000})
    slide_names = {s['name'] for s in existing_slides}
    sequence_no = 1
    for lesson_name, body in data['lessons']:
        slide_name = PREFIX + lesson_name
        if slide_name not in slide_names:
            call('slide.slide', 'create', [{
                'name': slide_name,
                'channel_id': channel_id,
                'slide_category': 'article',
                'slide_type': 'article',
                'source_type': 'local_file',
                'html_content': '<article>%s</article>' % body,
                'description': body,
                'completion_time': 8.0,
                'sequence': sequence_no,
                'is_preview': True,
                'is_published': True,
                'website_published': True,
                'user_id': uid,
            }])
        sequence_no += 1

    quiz_name, questions = data['quiz']
    quiz_title = PREFIX + quiz_name
    if quiz_title not in slide_names:
        quiz_id = call('slide.slide', 'create', [{
            'name': quiz_title,
            'channel_id': channel_id,
            'slide_category': 'quiz',
            'slide_type': 'quiz',
            'source_type': 'local_file',
            'description': '<p>Choose the best answer for each question. This is sample practice content.</p>',
            'completion_time': 5.0,
            'sequence': sequence_no,
            'is_published': True,
            'website_published': True,
            'user_id': uid,
        }])
        for q_index, (question_text, options, correct_index) in enumerate(questions, 1):
            question_id = call('slide.question', 'create', [{
                'slide_id': quiz_id,
                'question': question_text,
                'sequence': q_index,
            }])
            answer_vals = [{
                'question_id': question_id,
                'text_value': option,
                'is_correct': option_index == correct_index,
                'sequence': option_index + 1,
            } for option_index, option in enumerate(options)]
            call('slide.answer', 'create', [answer_vals])

# Enroll the first 50 imported sample students. Rotate them across all courses.
students = call('op.student', 'search_read', [[('gr_no', 'like', 'US26-%')]],
                {'fields': ['id', 'partner_id'], 'limit': 1000})
channel_ids = [channel_map[PREFIX + data['name']] for data in courses]
existing_members = call('slide.channel.partner', 'search_read',
    [[('channel_id', 'in', channel_ids)]], {'fields': ['channel_id', 'partner_id'], 'limit': 10000})
member_keys = {(row['channel_id'][0], row['partner_id'][0])
               for row in existing_members if row.get('channel_id') and row.get('partner_id')}
statuses = ['joined', 'ongoing', 'completed', 'invited']
member_vals = []
for index, student in enumerate(students):
    if not student.get('partner_id'):
        continue
    partner_id = student['partner_id'][0]
    # Give every student two courses to create a useful attendee distribution.
    for channel_offset in (index % len(channel_ids), (index + 1) % len(channel_ids)):
        channel_id = channel_ids[channel_offset]
        if (channel_id, partner_id) in member_keys:
            continue
        member_vals.append({
            'channel_id': channel_id,
            'partner_id': partner_id,
            'member_status': statuses[(index + channel_offset) % len(statuses)],
        })
        member_keys.add((channel_id, partner_id))
if member_vals:
    call('slide.channel.partner', 'create', [member_vals])

print('eLearning courses:', call('slide.channel', 'search_count',
    [[('name', 'like', PREFIX + '%')]]))
print('eLearning content and quizzes:', call('slide.slide', 'search_count',
    [[('channel_id', 'in', channel_ids)]]))
print('Quiz questions:', call('slide.question', 'search_count',
    [[('slide_id.channel_id', 'in', channel_ids)]]))
print('Quiz answers:', call('slide.answer', 'search_count',
    [[('question_id.slide_id.channel_id', 'in', channel_ids)]]))
print('Course enrollments:', call('slide.channel.partner', 'search_count',
    [[('channel_id', 'in', channel_ids)]]))
