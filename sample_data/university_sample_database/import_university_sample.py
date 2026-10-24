import csv, datetime, os, xmlrpc.client

BASE = os.path.dirname(os.path.abspath(__file__))
URL = 'http://localhost:8069'
DB = 'openeducat'
USER = 'admin'
PASSWORD = 'admin'
PREFIX = 'US26-'
common = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PASSWORD, {})
if not uid:
    raise SystemExit('Could not authenticate to the Odoo database.')
models = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/object')
def call(model, method, args=None, kwargs=None):
    return models.execute_kw(DB, uid, PASSWORD, model, method, args or [], kwargs or {})
def rows(table):
    with open(os.path.join(BASE, table + '.csv'), newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))
def m2o(value):
    return int(value) if value not in ('', None) else False
def existing(model, field, prefix=PREFIX):
    recs = call(model, 'search_read', [[(field, 'like', prefix + '%')]], {'fields': [field], 'limit': 50000})
    return {r[field]: r['id'] for r in recs}
def bulk(model, field, values):
    # values are (key, vals); match previously imported records by stable source key.
    found = existing(model, field)
    pending = [(key, vals) for key, vals in values if key not in found]
    if pending:
        ids = call(model, 'create', [[v for _, v in pending]])
        if isinstance(ids, int): ids = [ids]
        found.update({key: rid for (key, _), rid in zip(pending, ids)})
    return found

D=rows('departments'); C=rows('courses'); S=rows('subjects') if os.path.exists(os.path.join(BASE,'subjects.csv')) else []
P={int(r['id']):r for r in rows('people')}
inst=rows('instructors'); sem=rows('semesters'); sections=rows('sections'); students=rows('students')
enroll=rows('enrollments'); exams=rows('exams'); scores=rows('exam_results')

# Map source departments to OpenEduCat departments.
dep_vals=[]
for r in D:
    key=PREFIX+'D%04d'%int(r['id'])
    dep_vals.append((key, {'name':'[Sample University] '+r['name'], 'code':key}))
dep_map=bulk('op.department','code',dep_vals)

# Courses and one subject per course (the exam module assesses subjects).
subject_vals=[]; course_vals=[]
for r in C:
    sid=int(r['id']); skey=PREFIX+'S%04d'%sid; ckey=PREFIX+'C%04d'%sid
    subject_vals.append((skey, {'name':'[Sample] '+r['title'], 'code':skey, 'type':'theory', 'subject_type':'compulsory', 'department_id':dep_map[PREFIX+'D%04d'%int(r['department_id'])]}))
subject_map=bulk('op.subject','code',subject_vals)
for r in C:
    sid=int(r['id']); ckey=PREFIX+'C%04d'%sid; skey=PREFIX+'S%04d'%sid
    course_vals.append((ckey, {'name':'[Sample University] '+r['title'], 'code':ckey,
        'evaluation_type':'normal', 'department_id':dep_map[PREFIX+'D%04d'%int(r['department_id'])],
        'subject_ids':[(6,0,[subject_map[skey]])]}))
course_map=bulk('op.course','code',course_vals)

# Preserve sample faculty identities and connect each to its section exams.
faculty_values=[]; faculty_pending=[]
for r in inst:
    pid=int(r['person_id']); p=P[pid]; key=PREFIX+'STAFF%03d'%int(r['id'])
    email='usample.person%d@sample.invalid'%pid
    faculty_values.append((key, {'email':email}))
# create missing partners and faculty; map faculty by deterministic email.
faculty_map={r['email']:r['id'] for r in call('op.faculty','search_read',[[('email','like','usample.%@sample.invalid')]],{'fields':['email'],'limit':1000})}
missing=[r for r in inst if 'usample.person%d@sample.invalid'%int(r['person_id']) not in faculty_map]
if missing:
    partner_ids=call('res.partner','create',[[{'name':'[Sample] '+P[int(r['person_id'])]['first_name']+' '+P[int(r['person_id'])]['last_name'],
      'email':'usample.person%d@sample.invalid'%int(r['person_id']), 'phone':P[int(r['person_id'])].get('phone') or False,
      'is_company':False} for r in missing]])
    if isinstance(partner_ids,int): partner_ids=[partner_ids]
    fvals=[]
    for r,pid in zip(missing,partner_ids):
        person=P[int(r['person_id'])]; gender=person['gender']
        # OpenEduCat faculty supports male/female only; use its supported values for this synthetic sample.
        fg=gender if gender in ('male','female') else 'female'
        dep=dep_map[PREFIX+'D%04d'%int(r['department_id'])]
        fvals.append({'partner_id':pid,'first_name':person['first_name'],'last_name':person['last_name'],
            'birth_date':person['date_of_birth'],'gender':fg,'main_department_id':dep,'autopost_bills':'never'})
    call('op.faculty','create',[fvals])
faculty_map={r['email']:r['id'] for r in call('op.faculty','search_read',[[('email','like','usample.%@sample.invalid')]],{'fields':['email'],'limit':1000})}
faculty_by_source={int(r['id']):faculty_map['usample.person%d@sample.invalid'%int(r['person_id'])] for r in inst}

# Academic years and semester terms used by batches and enrollments.
year_map={}
for year in sorted({int(r['year']) for r in sem}):
    name=f'[Sample University] {year}'
    hit=call('op.academic.year','search_read',[[('name','=',name)]],{'fields':['id'],'limit':1})
    year_map[year]=hit[0]['id'] if hit else call('op.academic.year','create',[{'name':name,'start_date':f'{year}-01-01','end_date':f'{year}-12-31','term_structure':'others'}])
term_map={}
for r in sem:
    y=int(r['year']); season=r['season']; name=f'[Sample University] {season.title()} {y}'
    hit=call('op.academic.term','search_read',[[('name','=',name),('academic_year_id','=',year_map[y])]],{'fields':['id'],'limit':1})
    term_map[int(r['id'])]=hit[0]['id'] if hit else call('op.academic.term','create',[{'name':name,'term_start_date':r['start_date'],'term_end_date':r['end_date'],'academic_year_id':year_map[y]}])

# Students, with non-deliverable .invalid email addresses.
student_ids={}
missing_students=[]
current_students=existing('op.student','gr_no')
for r in students:
    key=PREFIX+'STU%04d'%int(r['id'])
    if key in current_students: student_ids[int(r['id'])]=current_students[key]
    else: missing_students.append(r)
if missing_students:
    pp=[]
    for r in missing_students:
        p=P[int(r['person_id'])]
        pp.append({'name':'[Sample] '+p['first_name']+' '+p['last_name'],
                   'email':'usample.student%d@sample.invalid'%int(r['person_id']),
                   'phone':p.get('phone') or False,'is_company':False})
    partners=call('res.partner','create',[pp]); partners=[partners] if isinstance(partners,int) else partners
    sv=[]
    for r,partner in zip(missing_students,partners):
        p=P[int(r['person_id'])]; g=p['gender']
        gender={'male':'m','female':'f'}.get(g,'o')
        sv.append({'partner_id':partner,'first_name':p['first_name'],'last_name':p['last_name'],
            'birth_date':p['date_of_birth'],'gender':gender,'gr_no':PREFIX+'STU%04d'%int(r['id']),
            'autopost_bills':'never'})
    newids=call('op.student','create',[sv]); newids=[newids] if isinstance(newids,int) else newids
    for r,rid in zip(missing_students,newids): student_ids[int(r['id'])]=rid
for r in students:
    key=PREFIX+'STU%04d'%int(r['id'])
    if int(r['id']) not in student_ids: student_ids[int(r['id'])]=current_students[key]

# Batches mirror the sample's 40 course sections; each section has its source instructor.
section_by_id={int(r['id']):r for r in sections}
semester_by_id={int(r['id']):r for r in sem}
batch_vals=[]
for r in sections:
    n=int(r['id']); code=PREFIX+'B%04d'%n; semrow=semester_by_id[int(r['semester_id'])]
    batch_vals.append((code,{'name':'[Sample] Section %d'%n,'code':code,
        'start_date':semrow['start_date'],'end_date':semrow['end_date'],
        'course_id':course_map[PREFIX+'C%04d'%int(r['course_id'])]}))
batch_map=bulk('op.batch','code',batch_vals)

# Enrollments preserve the course, section/batch and student relationships.
existing_enroll=call('op.student.course','search_read',[[('student_id','in',list(student_ids.values())),('batch_id','in',[batch_map[PREFIX+'B%04d'%int(s['id'])] for s in sections])]],{'fields':['student_id','course_id','batch_id']})
enroll_pairs={(x['student_id'][0],x['course_id'][0],x['batch_id'][0]) for x in existing_enroll if x.get('student_id') and x.get('course_id') and x.get('batch_id')}
evals=[]
for r in enroll:
    sec=section_by_id[int(r['section_id'])]; sid=int(r['student_id']); cid=int(sec['course_id']); bid=batch_map[PREFIX+'B%04d'%int(sec['id'])]
    tup=(student_ids[sid],course_map[PREFIX+'C%04d'%cid],bid)
    if tup not in enroll_pairs:
        erow=semester_by_id[int(sec['semester_id'])]; year=int(erow['year'])
        ev={'student_id':tup[0],'course_id':tup[1],'batch_id':bid,'roll_number':PREFIX+'%04d-%04d'%(sid,int(sec['id'])),
            'academic_years_id':year_map[year],'academic_term_id':term_map[int(sec['semester_id'])],
            'state':'finished' if r.get('letter_grade') not in ('','W') else 'running'}
        evals.append(ev); enroll_pairs.add(tup)
if evals: call('op.student.course','create',[evals])

# One exam session per section, two scheduled exams on average, and linked sample scores.
by_section={}
for r in exams: by_section.setdefault(int(r['section_id']),[]).append(r)
exam_type=call('op.exam.type','search_read',[[('code','=',PREFIX+'ET')]],{'fields':['id'],'limit':1})
exam_type=exam_type[0]['id'] if exam_type else call('op.exam.type','create',[{'name':'[Sample] University exam','code':PREFIX+'ET'}])
session_vals=[]
for secid, erows in by_section.items():
    dates=sorted(e['exam_date'][:10] for e in erows); sec=section_by_id[secid]
    key=PREFIX+'ES%04d'%secid
    session_vals.append((key,{'name':'[Sample] Section %d exam session'%secid,
      'course_id':course_map[PREFIX+'C%04d'%int(sec['course_id'])],
      'batch_id':batch_map[PREFIX+'B%04d'%secid], 'exam_code':key,
      'start_date':dates[0],'end_date':(datetime.date.fromisoformat(dates[-1])+datetime.timedelta(days=1)).isoformat(), 'exam_type':exam_type,'evaluation_type':'normal','state':'done'}))
session_map=existing('op.exam.session','exam_code')
for key, vals in session_vals:
    if key not in session_map: session_map[key]=call('op.exam.session','create',[vals])
    else: call('op.exam.session','write',[[session_map[key]],{'end_date':vals['end_date']}])
exam_vals=[]
for r in exams:
    eid=int(r['id']); sec=section_by_id[int(r['section_id'])]; key=PREFIX+'EX%04d'%eid
    start=datetime.datetime.strptime(r['exam_date'],'%Y-%m-%d %H:%M:%S')
    end=start+datetime.timedelta(minutes=int(r['duration_minutes']))
    exam_vals.append((key,{'name':'[Sample] '+r['title']+' — '+C[int(sec['course_id'])-1]['title'],
       'exam_code':key,'session_id':session_map[PREFIX+'ES%04d'%int(sec['id'])],
       'subject_id':subject_map[PREFIX+'S%04d'%int(sec['course_id'])],
       'start_time':start.strftime('%Y-%m-%d %H:%M:%S'),'end_time':end.strftime('%Y-%m-%d %H:%M:%S'),
       'total_marks':int(r['max_points']),'min_marks':50,
       'responsible_id':[(6,0,[faculty_by_source[int(sec['instructor_id'])]])], 'state':'result_updated'}))
exam_map=bulk('op.exam','exam_code',exam_vals)

# Results are native OpenEduCat result lines, not raw SQL inserts.
score_exam_ids=[exam_map[PREFIX+'EX%04d'%int(r['exam_id'])] for r in scores]
existing_lines=call('op.result.line','search_read',[[('exam_id','in',score_exam_ids)]],{'fields':['exam_id','student_id'],'limit':50000})
result_pairs={(x['exam_id'][0],x['student_id'][0]) for x in existing_lines if x.get('exam_id') and x.get('student_id')}
result_vals=[]
for r in scores:
    pair=(exam_map[PREFIX+'EX%04d'%int(r['exam_id'])],student_ids[int(r['student_id'])])
    if pair not in result_pairs:
        result_vals.append({'exam_id':pair[0],'student_id':pair[1],'marks':int(r['score'])})
        result_pairs.add(pair)
if result_vals: call('op.result.line','create',[result_vals])

# These marks drive OpenEduCat's exam-level Results Entered flag and attendee list.
existing_attendees=call('op.exam.attendees','search_read',[[('exam_id','in',score_exam_ids)]],{'fields':['exam_id','student_id'],'limit':50000})
attendee_pairs={(x['exam_id'][0],x['student_id'][0]) for x in existing_attendees if x.get('exam_id') and x.get('student_id')}
attendee_vals=[]
for r in scores:
    pair=(exam_map[PREFIX+'EX%04d'%int(r['exam_id'])],student_ids[int(r['student_id'])])
    if pair not in attendee_pairs:
        attendee_vals.append({'exam_id':pair[0],'student_id':pair[1],'marks':int(r['score']),'status':'present'})
        attendee_pairs.add(pair)
if attendee_vals: call('op.exam.attendees','create',[attendee_vals])

# Sample assignments and student submissions.
assignment_rows=rows('assignments')
submission_rows=rows('submissions')
assignment_type=call('grading.assignment.type','search_read',[[('code','=',PREFIX+'AT')]],{'fields':['id'],'limit':1})
assignment_type=assignment_type[0]['id'] if assignment_type else call('grading.assignment.type','create',[{'name':'[Sample] University assignments','code':PREFIX+'AT','assign_type':'sub'}])
assignment_parent_vals=[]
for r in assignment_rows:
    aid=int(r['id']); sec=section_by_id[int(r['section_id'])]
    key=PREFIX+'A%04d'%aid+' | '+r['title']
    due=datetime.datetime.strptime(r['due_date'],'%Y-%m-%d %H:%M:%S')
    issued=due-datetime.timedelta(days=14)
    assignment_parent_vals.append((key,{'name':key,
        'course_id':course_map[PREFIX+'C%04d'%int(sec['course_id'])],
        'subject_id':subject_map[PREFIX+'S%04d'%int(sec['course_id'])],
        'issued_date':issued.strftime('%Y-%m-%d %H:%M:%S'),
        'assignment_type':assignment_type,
        'faculty_id':faculty_by_source[int(sec['instructor_id'])],
        'point':float(r['max_points'])}))
parent_map=bulk('grading.assignment','name',assignment_parent_vals)
assignment_vals=[]
section_enrolled={}
for e in enroll:
    sec=section_by_id[int(e['section_id'])]
    section_enrolled.setdefault(int(sec['id']),set()).add(student_ids[int(e['student_id'])])
for r in assignment_rows:
    aid=int(r['id']); sec=section_by_id[int(r['section_id'])]
    key=PREFIX+'A%04d'%aid+' | '+r['title']
    due=datetime.datetime.strptime(r['due_date'],'%Y-%m-%d %H:%M:%S')
    assignment_vals.append((key,{'grading_assignment_id':parent_map[key],
        'batch_id':batch_map[PREFIX+'B%04d'%int(sec['id'])],
        'marks':float(r['max_points']),
        'description':'[Public sample] '+r['description']+'; assignment data from the University Sample Database.',
        'submission_date':due.strftime('%Y-%m-%d %H:%M:%S'),
        'state':'finish','allocation_ids':[(6,0,sorted(section_enrolled.get(int(sec['id']),set())))],
        'courses_subjects':[(6,0,[subject_map[PREFIX+'S%04d'%int(sec['course_id'])]])]}))
assignment_map=bulk('op.assignment','name',assignment_vals)
assignment_id_by_source={int(r['id']):assignment_map[PREFIX+'A%04d'%int(r['id'])+' | '+r['title']] for r in assignment_rows}
existing_submissions=call('op.assignment.sub.line','search_read',[[('assignment_id','in',list(assignment_id_by_source.values()))]],{'fields':['assignment_id','student_id'],'limit':50000})
submission_pairs={(x['assignment_id'][0],x['student_id'][0]) for x in existing_submissions if x.get('assignment_id') and x.get('student_id')}
submission_vals=[]
for r in submission_rows:
    pair=(assignment_id_by_source[int(r['assignment_id'])],student_ids[int(r['student_id'])])
    if pair in submission_pairs: continue
    marks=float(r['grade_earned']) if r.get('grade_earned') else False
    submission_vals.append({'assignment_id':pair[0],'student_id':pair[1],
        'description':'[Public sample] Student submission record.',
        'submission_date':r['submission_time'], 'marks':marks,
        'note':r.get('feedback') or False,'state':'accept' if marks is not False else 'submit'})
    submission_pairs.add(pair)
if submission_vals: call('op.assignment.sub.line','create',[submission_vals])

# Sample admission intake registers and applications derived from the sample student/person rows.
applicant_rows=[]
for r in students:
    person=P[int(r['person_id'])]
    if person['gender'] in ('male','female'):
        applicant_rows.append((r,person))
    if len(applicant_rows)>=30: break
if len(applicant_rows)<30:
    raise RuntimeError('Not enough source students with gender values supported by the admission form.')
course_source_ids=[int(r['id']) for r in C[:5]]
register_vals=[]
for idx,cid in enumerate(course_source_ids,1):
    key=PREFIX+'REG%02d'%idx
    register_name=key+' | 2025 admissions - '+C[cid-1]['title']
    register_vals.append((register_name,{'name':register_name,
      'start_date':'2025-01-01','end_date':'2025-12-31','course_id':course_map[PREFIX+'C%04d'%cid],
      'min_count':5,'max_count':50,'minimum_age_criteria':3,
      'academic_years_id':year_map[2025],'state':'application','admission_base':'course'}))
register_map=bulk('op.admission.register','name',register_vals)
application_states=(['draft']*5+['submit']*8+['confirm']*8+['pending']*4+['reject']*3+['admission']*2)
admission_vals=[]
for idx,(student_row,person) in enumerate(applicant_rows,1):
    sid=int(student_row['id']); cid=course_source_ids[(idx-1)%len(course_source_ids)]
    application_date=datetime.datetime(2025,3,1)+datetime.timedelta(days=(idx-1)*5)
    status=application_states[idx-1]
    name='[Sample] '+person['first_name']+' '+person['last_name']
    vals={'application_number':PREFIX+'APP%04d'%idx,'name':name,
      'first_name':person['first_name'],'last_name':person['last_name'],
      'gender':'m' if person['gender']=='male' else 'f',
      'birth_date':person['date_of_birth'],'application_date':application_date.strftime('%Y-%m-%d %H:%M:%S'),
      'course_id':course_map[PREFIX+'C%04d'%cid],
      'register_id':register_map[PREFIX+'REG%02d'%((idx-1)%len(course_source_ids)+1)+' | 2025 admissions - '+C[course_source_ids[(idx-1)%len(course_source_ids)]-1]['title']],
      'email':'usample.applicant%d@sample.invalid'%int(person['id']),
      'phone':person.get('phone') or False,'mobile':person.get('phone') or False,
      'fees':1000.0,'state':status,'is_student':True,
      'student_id':student_ids[sid],
      'partner_id':call('op.student','read',[[student_ids[sid]],['partner_id']])[0]['partner_id'][0]}
    if status=='admission': vals['admission_date']=application_date.date().isoformat()
    admission_vals.append((PREFIX+'APP%04d'%idx,vals))
admission_map=bulk('op.admission','application_number',admission_vals)

print('Imported university sample data into',DB)
for label,model,domain in [
 ('departments','op.department',[('code','like',PREFIX+'D%')]),
 ('courses','op.course',[('code','like',PREFIX+'C%')]),
 ('subjects','op.subject',[('code','like',PREFIX+'S%')]),
 ('faculty','op.faculty',[('email','like','usample.person%@sample.invalid')]),
 ('students','op.student',[('gr_no','like',PREFIX+'STU%')]),
 ('batches','op.batch',[('code','like',PREFIX+'B%')]),
 ('enrollments','op.student.course',[('roll_number','like',PREFIX+'%')]),
 ('exam sessions','op.exam.session',[('exam_code','like',PREFIX+'ES%')]),
 ('exams','op.exam',[('exam_code','like',PREFIX+'EX%')]),
 ('exam results','op.result.line',[('exam_id','in',score_exam_ids)])]:
 print(f'{label}:',call(model,'search_count',[domain]))











print('Assignments:',call('op.assignment','search_count',[[('name','like',PREFIX+'A%')]]))
print('Assignment submissions:',call('op.assignment.sub.line','search_count',[[('assignment_id.name','like',PREFIX+'A%')]]))


