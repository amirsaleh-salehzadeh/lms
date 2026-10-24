"""Idempotently seed SIS reference data in the local OpenEduCat demo DB."""
import xmlrpc.client

URL = 'http://localhost:8069'
DB = 'openeducat'
LOGIN = 'admin'
PASSWORD = 'admin'
P = 'US26-'
common = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/common', allow_none=True)
uid = common.authenticate(DB, LOGIN, PASSWORD, {})
if not uid:
    raise SystemExit('Could not authenticate to the local OpenEduCat database')
models = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/object', allow_none=True)


def call(model, method, args=None, kwargs=None):
    return models.execute_kw(DB, uid, PASSWORD, model, method, args or [], kwargs or {})


def existing(model, field, prefix=P):
    rows = call(model, 'search_read', [[(field, 'like', prefix + '%')]],
                {'fields': [field], 'limit': 10000})
    return {row[field]: row['id'] for row in rows}


def ensure_many(model, field, rows):
    found = existing(model, field)
    for key, values in rows:
        if key not in found:
            record_id = call(model, 'create', [values])
            found[key] = record_id if isinstance(record_id, int) else record_id[0]
    return found


# SIS categories, program levels, and programs, linked to the imported departments.
categories = ensure_many('op.category', 'code', [
    (P + 'CAT-UG', {'name': 'Sample Undergraduate', 'code': P + 'CAT-UG'}),
    (P + 'CAT-PG', {'name': 'Sample Postgraduate', 'code': P + 'CAT-PG'}),
    (P + 'CAT-CERT', {'name': 'Sample Certificate', 'code': P + 'CAT-CERT'}),
    (P + 'CAT-ONLINE', {'name': 'Sample Online', 'code': P + 'CAT-ONLINE'}),
    (P + 'CAT-FOUND', {'name': 'Sample Foundation', 'code': P + 'CAT-FOUND'}),
])
levels = ensure_many('op.program.level', 'name', [
    (P + 'Level 1 - Foundation', {'name': P + 'Level 1 - Foundation'}),
    (P + 'Level 2 - Undergraduate', {'name': P + 'Level 2 - Undergraduate'}),
    (P + 'Level 3 - Postgraduate', {'name': P + 'Level 3 - Postgraduate'}),
    (P + 'Level 4 - Certificate', {'name': P + 'Level 4 - Certificate'}),
])
departments = call('op.department', 'search_read', [[]], {'fields': ['id', 'name'], 'limit': 100})
dept_ids = [x['id'] for x in departments]
program_rows = [
    ('US26-P-UGBUS', 'Sample Bachelor of Business', 'Level 2 - Undergraduate', 120, 12),
    ('US26-P-UGCOMP', 'Sample Bachelor of Computing', 'Level 2 - Undergraduate', 120, 12),
    ('US26-P-PGDATA', 'Sample Master of Data Science', 'Level 3 - Postgraduate', 48, 8),
    ('US26-P-CERTPM', 'Sample Project Management Certificate', 'Level 4 - Certificate', 36, 6),
    ('US26-P-FOUND', 'Sample Foundation in Science', 'Level 1 - Foundation', 48, 8),
]
program_map = existing('op.program', 'code')
existing_programs = call('op.program', 'search_read', [[]],
                         {'fields': ['id', 'name', 'code'], 'limit': 1000})
program_by_name = {x['name']: x for x in existing_programs}
for idx, (code, name, level, max_load, min_load) in enumerate(program_rows):
    prior = program_by_name.get(name)
    if prior:
        if prior['code'] != code:
            call('op.program', 'write', [[prior['id']], {'code': code}])
        program_map[code] = prior['id']
    elif code not in program_map:
        vals = {'name': name, 'code': code, 'program_level_id': levels[P + level],
                'max_unit_load': max_load, 'min_unit_load': min_load}
        if dept_ids:
            vals['department_id'] = dept_ids[idx % len(dept_ids)]
        program_map[code] = call('op.program', 'create', [vals])

# Three academic terms for the imported 2025/26 year.
years = call('op.academic.year', 'search_read', [[]], {'fields': ['id', 'name'], 'limit': 100})
year = next((y for y in years if '2025' in y['name'] or '2026' in y['name']), years[0] if years else None)
if not year:
    raise RuntimeError('No academic year exists; import the university sample data first')
term_rows = [
    (P + 'Term 1 - 2025/26', '2025-09-01', '2025-12-19'),
    (P + 'Term 2 - 2025/26', '2026-02-02', '2026-05-29'),
    (P + 'Term 3 - 2025/26', '2026-08-03', '2026-12-18'),
]
terms = call('op.academic.term', 'search_read', [[('name', 'like', P + 'Term%')]],
             {'fields': ['id', 'name'], 'limit': 100})
term_map = {x['name']: x['id'] for x in terms}
for name, start, end in term_rows:
    if name not in term_map:
        term_map[name] = call('op.academic.term', 'create', [{
            'name': name, 'term_start_date': start, 'term_end_date': end,
            'academic_year_id': year['id']}])

# Fee plans with valid 100% installment splits.
fee_rows = [
    ('UG', 'Sample Undergraduate Tuition Plan', [0.5, 0.3, 0.2]),
    ('PG', 'Sample Postgraduate Tuition Plan', [0.4, 0.3, 0.3]),
    ('CERT', 'Sample Certificate Fee Plan', [0.6, 0.4]),
]
fee_map = existing('op.fees.terms', 'code')
for suffix, name, shares in fee_rows:
    code = P + 'FEE-' + suffix
    if code not in fee_map:
        line_commands = [(0, 0, {'due_days': days, 'value': share * 100})
                         for days, share in zip([0, 30, 60], shares)]
        fee_map[code] = call('op.fees.terms', 'create', [{
            'name': name, 'code': code, 'fees_terms': 'fixed_days',
            'no_days': 30, 'day_type': 'after',
            'note': 'Generated demo fee schedule; amounts are represented by installments.',
            'line_ids': line_commands}])

# Classrooms mapped to the already imported batches/courses and furnished with facilities.
facility_names = [('LECT', 'Lecture Screen'), ('PROJ', 'Projector'),
                  ('WHITE', 'Whiteboard'), ('WIFI', 'Wi-Fi Access'),
                  ('LAB', 'Computer Workstations'), ('ACCESS', 'Accessible Seating')]
facilities = ensure_many('op.facility', 'code', [
    (P + 'FAC-' + code, {'name': P + name, 'code': P + 'FAC-' + code})
    for code, name in facility_names])
batches = call('op.batch', 'search_read', [[('code', 'like', P + 'B%')]],
               {'fields': ['id', 'code', 'course_id'], 'limit': 100})
classrooms = existing('op.classroom', 'code')
for idx in range(12):
    code = P + 'ROOM-%02d' % (idx + 1)
    if code not in classrooms:
        vals = {'name': 'Sample Room %02d' % (idx + 1), 'code': code,
                'capacity': [24, 30, 36, 40][idx % 4]}
        if batches:
            batch = batches[idx % len(batches)]
            vals['batch_id'] = batch['id']
            if batch.get('course_id'):
                vals['course_id'] = batch['course_id'][0]
        classrooms[code] = call('op.classroom', 'create', [vals])
classroom_rows = call('op.classroom', 'search_read', [[('code', 'like', P + 'ROOM-%')]],
                      {'fields': ['id', 'code'], 'limit': 100})
facility_line_pairs = call('op.facility.line', 'search_read',
    [[('classroom_id.code', 'like', P + 'ROOM-%')]],
    {'fields': ['classroom_id', 'facility_id'], 'limit': 1000})
facility_pairs = {(x['classroom_id'][0], x['facility_id'][0])
                  for x in facility_line_pairs if x.get('classroom_id') and x.get('facility_id')}
facility_ids = [facilities[P + 'FAC-' + code] for code, _ in facility_names]
for idx, room in enumerate(classroom_rows):
    for offset in range(3):
        facility_id = facility_ids[(idx + offset) % len(facility_ids)]
        pair = (room['id'], facility_id)
        if pair not in facility_pairs:
            call('op.facility.line', 'create', [{'classroom_id': room['id'],
                'facility_id': facility_id, 'quantity': 1 if offset != 1 else 2}])
            facility_pairs.add(pair)

# Parent relationship categories and one non-deliverable sample guardian per student.
relationship_names = ['Mother', 'Father', 'Guardian', 'Other']
relation_map = {}
existing_rel = call('op.parent.relationship', 'search_read', [[]], {'fields': ['id', 'name'], 'limit': 100})
for name in relationship_names:
    found = next((x for x in existing_rel if x['name'].lower() == name.lower()), None)
    relation_map[name] = found['id'] if found else call('op.parent.relationship', 'create', [{'name': name}])
sample_students = call('op.student', 'search_read', [[('gr_no', 'like', P + '%')]],
                       {'fields': ['id', 'name', 'gr_no', 'category_id'], 'limit': 1000})
parent_records = call('op.parent', 'search_read',
                      [[('student_ids', 'in', [s['id'] for s in sample_students])]],
                      {'fields': ['id', 'student_ids'], 'limit': 1000}) if sample_students else []
linked_student_ids = {sid for parent in parent_records for sid in parent.get('student_ids', [])}
for idx, student in enumerate(sample_students):
    category_code = [P + 'CAT-UG', P + 'CAT-PG', P + 'CAT-CERT', P + 'CAT-ONLINE', P + 'CAT-FOUND'][idx % 5]
    if not student.get('category_id'):
        call('op.student', 'write', [[student['id']], {'category_id': categories[category_code]}])
    if student['id'] in linked_student_ids:
        continue
    rel_name = relationship_names[idx % len(relationship_names)]
    partner_name = 'Sample Guardian %02d' % (idx + 1)
    partner_id = call('res.partner', 'create', [{'name': partner_name,
        'email': 'guardian%02d@sample.invalid' % (idx + 1),
        'phone': '+270000%06d' % (idx + 1), 'is_parent': True}])
    call('op.parent', 'create', [{'name': partner_id,
        'email': 'guardian%02d@sample.invalid' % (idx + 1),
        'mobile': '+270000%06d' % (idx + 1), 'relationship_id': relation_map[rel_name],
        'student_ids': [(6, 0, [student['id']])]}])

for label, model, domain in [
    ('Categories', 'op.category', [('code', 'like', P + 'CAT-%')]),
    ('Program levels', 'op.program.level', [('name', 'like', P + '%')]),
    ('Programs', 'op.program', [('code', 'like', P + 'P-%')]),
    ('Academic terms', 'op.academic.term', [('name', 'like', P + 'Term%')]),
    ('Fee plans', 'op.fees.terms', [('code', 'like', P + 'FEE-%')]),
    ('Classrooms', 'op.classroom', [('code', 'like', P + 'ROOM-%')]),
    ('Facilities', 'op.facility', [('code', 'like', P + 'FAC-%')]),
    ('Parent records', 'op.parent', [('name.email', 'like', 'guardian%@sample.invalid')]),
]:
    print('%s: %s' % (label, call(model, 'search_count', [domain])))
print('Sample students categorized: %s' % call('op.student', 'search_count',
    [[('gr_no', 'like', P + '%'), ('category_id', '!=', False)]]))
