import csv, datetime, html, os, xmlrpc.client
BASE=os.path.dirname(os.path.abspath(__file__))
URL='http://localhost:8069'; DB='openeducat'; USER='admin'; PASSWORD='admin'; P='US26-'
common=xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/common',allow_none=True)
uid=common.authenticate(DB,USER,PASSWORD,{})
if not uid: raise SystemExit('Odoo authentication failed')
models=xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/object',allow_none=True)
def call(model,method,args=None,kwargs=None):
    return models.execute_kw(DB,uid,PASSWORD,model,method,args or [],kwargs or {})
def rows(name):
    with open(os.path.join(BASE,name+'.csv'),newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))
def existing(model,field,prefix=P):
    recs=call(model,'search_read',[[(field,'like',prefix+'%')]],{'fields':[field],'limit':50000})
    return {r[field]:r['id'] for r in recs}
def bulk(model,field,items):
    found=existing(model,field)
    pending=[(key,vals) for key,vals in items if key not in found]
    if pending:
        ids=call(model,'create',[[vals for _,vals in pending]])
        ids=[ids] if isinstance(ids,int) else ids
        found.update({key:rid for (key,_),rid in zip(pending,ids)})
    return found

people={int(r['id']):r for r in rows('people')}
students=rows('students'); instructors=rows('instructors'); sections={int(r['id']):r for r in rows('sections')}
enrollments=rows('enrollments'); courses=rows('courses'); schedules=rows('schedules')
course_map=existing('op.course','code'); subject_map=existing('op.subject','code'); batch_map=existing('op.batch','code')
student_map=existing('op.student','gr_no')
faculty_by_source={}
fac=call('op.faculty','search_read',[[('email','like','usample.person%@sample.invalid')]],{'fields':['email'],'limit':1000})
fac_by_email={x['email']:x['id'] for x in fac}
for r in instructors: faculty_by_source[int(r['id'])]=fac_by_email['usample.person%d@sample.invalid'%int(r['person_id'])]

# Convert all sample teaching staff into linked HR employees.
faculties=call('op.faculty','search_read',[[('email','like','usample.person%@sample.invalid')]],{'fields':['emp_id'],'limit':1000})
needs_employee=[x['id'] for x in faculties if not x.get('emp_id')]
if needs_employee: call('op.faculty','create_employee',[needs_employee])

# Timetable periods and the 60 public sample schedules.
weekdays=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
time_parts={}
for r in schedules:
    hh,mm,_=map(int,r['start_time'].split(':'))
    ampm='am' if hh<12 else 'pm'; hour=hh%12 or 12
    time_parts[r['start_time']]=(str(hour),f'{mm:02d}',ampm)
timing_vals=[]
for idx,clock in enumerate(sorted(time_parts),1):
    key=P+'TIME%02d'%idx; hour,minute,ampm=time_parts[clock]
    timing_vals.append((key,{'name':key,'hour':hour,'minute':minute,'am_pm':ampm,'duration':1.0,'sequence':idx}))
timing_map=bulk('op.timing','name',timing_vals)
timing_by_clock={clock:timing_map[P+'TIME%02d'%(idx+1)] for idx,clock in enumerate(sorted(time_parts))}
# Resolve current sessions by their stable batch/time/subject tuple.
batch_ids=[batch_map[P+'B%04d'%sid] for sid in sections]
existing_sessions=call('op.session','search_read',[[('batch_id','in',batch_ids),('start_datetime','>=','2025-09-01 00:00:00'),('start_datetime','<=','2025-09-30 23:59:59')]],{'fields':['batch_id','start_datetime','subject_id'],'limit':5000})
session_keys={(x['batch_id'][0],x['start_datetime'],x['subject_id'][0]) for x in existing_sessions if x.get('batch_id') and x.get('subject_id')}
section_students={}
for e in enrollments:
    sec=sections[int(e['section_id'])]
    section_students.setdefault(int(sec['id']),set()).add(student_map[P+'STU%04d'%int(e['student_id'])])
session_vals=[]
for r in schedules:
    sec=sections[int(r['section_id'])]; sid=int(sec['id']); source_course=int(sec['course_id'])
    day=weekdays.index(r['day_of_week'].lower())
    date=datetime.date(2025,9,1)+datetime.timedelta(days=day)
    start=datetime.datetime.combine(date,datetime.time.fromisoformat(r['start_time']))
    end=start+datetime.timedelta(hours=1)
    batch_id=batch_map[P+'B%04d'%sid]; subject_id=subject_map[P+'S%04d'%source_course]
    tup=(batch_id,start.strftime('%Y-%m-%d %H:%M:%S'),subject_id)
    if tup in session_keys: continue
    session_vals.append({'start_datetime':tup[1],'end_datetime':end.strftime('%Y-%m-%d %H:%M:%S'),
      'course_id':course_map[P+'C%04d'%source_course], 'faculty_id':faculty_by_source[int(sec['instructor_id'])],
      'batch_id':batch_id,'subject_id':subject_id,'timing_id':timing_by_clock[r['start_time']],
      'days':r['day_of_week'].lower(),'state':'confirm','student_ids':[(6,0,sorted(section_students.get(sid,set()))) ]})
    session_keys.add(tup)
if session_vals: call('op.session','create',[session_vals])
session_rows=call('op.session','search_read',[[('start_datetime','>=','2025-09-01 00:00:00'),('start_datetime','<=','2025-09-30 23:59:59'),('batch_id','in',batch_ids)]],{'fields':['id','batch_id','start_datetime','subject_id'],'limit':5000})
session_by_batch={}
for x in session_rows:
    session_by_batch.setdefault(x['batch_id'][0],x['id'])

# Attendance registers for ten populated sections, with three class-date sheets each.
attendance_type_vals=[]
for code,name,flags in [
 ('PRESENT','Present',{'present':True}),('LATE','Late',{'late':True}),
 ('EXCUSED','Excused absence',{'excused':True}),('ABSENT','Unexcused absence',{'absent':True})]:
    key=P+'ATT-'+code; attendance_type_vals.append((key,{'name':key,'present':flags.get('present',False),'late':flags.get('late',False),'excused':flags.get('excused',False),'absent':flags.get('absent',False)}))
attendance_types=bulk('op.attendance.type','name',attendance_type_vals)
section_ids=[sid for sid in sorted(sections) if section_students.get(sid)][:10]
register_vals=[]
for sid in section_ids:
    sec=sections[sid]; key=P+'AR%04d'%sid; cid=int(sec['course_id'])
    register_vals.append((key,{'name':key,'code':key,'course_id':course_map[P+'C%04d'%cid],
      'batch_id':batch_map[P+'B%04d'%sid],'subject_id':subject_map[P+'S%04d'%cid]}))
attendance_registers=bulk('op.attendance.register','code',register_vals)
att_dates=[datetime.date(2025,9,2)+datetime.timedelta(days=7*i) for i in range(3)]
existing_sheets=call('op.attendance.sheet','search_read',[[('register_id','in',[attendance_registers[P+'AR%04d'%sid] for sid in section_ids])]],{'fields':['register_id','attendance_date'],'limit':5000})
sheet_keys={(x['register_id'][0],x['attendance_date']) for x in existing_sheets if x.get('register_id')}
sheet_vals=[]
for sid in section_ids:
    reg=attendance_registers[P+'AR%04d'%sid]
    for date in att_dates:
        if (reg,date.isoformat()) not in sheet_keys:
            sheet_vals.append({'register_id':reg,'attendance_date':date.isoformat(),'state':'done'})
            sheet_keys.add((reg,date.isoformat()))
if sheet_vals: call('op.attendance.sheet','create',[sheet_vals])
sheets=call('op.attendance.sheet','search_read',[[('register_id','in',[attendance_registers[P+'AR%04d'%sid] for sid in section_ids])]],{'fields':['id','register_id','attendance_date'],'limit':5000})
sheets_by_key={(x['register_id'][0],x['attendance_date']):x['id'] for x in sheets}
existing_lines=call('op.attendance.line','search_read',[[('attendance_id','in',[x['id'] for x in sheets])]],{'fields':['attendance_id','student_id'],'limit':50000})
att_pairs={(x['attendance_id'][0],x['student_id'][0]) for x in existing_lines if x.get('attendance_id') and x.get('student_id')}
line_vals=[]
status_codes=['PRESENT','PRESENT','PRESENT','PRESENT','LATE','EXCUSED','ABSENT']
for sid in section_ids:
    reg=attendance_registers[P+'AR%04d'%sid]
    for date in att_dates:
        sheet_id=sheets_by_key[(reg,date.isoformat())]
        for student_id in sorted(section_students[sid]):
            if (sheet_id,student_id) in att_pairs: continue
            idx=(student_id+sid+date.day)%len(status_codes); status=status_codes[idx]
            line={'attendance_id':sheet_id,'student_id':student_id,
              'attendance_type_id':attendance_types[P+'ATT-'+status],
              'present':status=='PRESENT','late':status=='LATE',
              'excused':status=='EXCUSED','absent':status=='ABSENT',
              'remark':'[Sample attendance]'}
            line_vals.append(line);att_pairs.add((sheet_id,student_id))
if line_vals: call('op.attendance.line','create',[line_vals])

# Library catalog: all 2,000 public sample books, copies, student cards and 100 circulation rows.
books=rows('books'); loans=rows('book_loans')
media_type=bulk('op.media.type','code',[(P+'BOOK',{'name':'[Sample] Books','code':P+'BOOK'})])[P+'BOOK']
authors=sorted({r['author'] for r in books}); publishers=sorted({r['publisher'] for r in books})
author_names={v:P+'AU%04d'%i+' | '+v[:95] for i,v in enumerate(authors,1)}
publisher_names={v:P+'PU%04d'%i for i,v in enumerate(publishers,1)}
author_map=bulk('op.author','name',[(name,{'name':name}) for name in author_names.values()])
publisher_map=bulk('op.publisher','name',[(name,{'name':name}) for name in publisher_names.values()])
media_vals=[]
for r in books:
    bid=int(r['id']); key=P+'BOOK%04d'%bid
    an=author_names[r['author']]; pn=publisher_names[r['publisher']]
    media_vals.append((key,{'internal_code':key,'name':'[Sample] '+r['title'][:110],
      'isbn':r['isbn'],'edition':str(r['publication_year']),
      'description':'[Public CC0 sample] Publisher: '+r['publisher'],
      'media_type_id':media_type,'author_ids':[(6,0,[author_map[an]])],
      'publisher_ids':[(6,0,[publisher_map[pn]])]}))
media_map=bulk('op.media','internal_code',media_vals)
unit_vals=[]
for r in books:
    bid=int(r['id']); unitkey=P+'UNIT-B%04d-01'%bid
    unit_vals.append((unitkey,{'name':unitkey,'media_id':media_map[P+'BOOK%04d'%bid],'state':'available'}))
loan_unit_keys={int(r['id']):P+'UNIT-L%04d'%int(r['id']) for r in loans}
for loan in loans:
    key=loan_unit_keys[int(loan['id'])]
    unit_vals.append((key,{'name':key,'media_id':media_map[P+'BOOK%04d'%int(loan['book_id'])],
      'state':'available' if loan.get('return_date') else 'issue'}))
unit_map=bulk('op.media.unit','name',unit_vals)
card_type_map=existing('op.library.card.type','name')
for name,vals in [(P+'CARD-STUDENT',{'name':P+'CARD-STUDENT','allow_media':10,'duration':21,'penalty_amt_per_day':1.0}),(P+'CARD-FACULTY',{'name':P+'CARD-FACULTY','allow_media':20,'duration':30,'penalty_amt_per_day':1.0})]:
    if name not in card_type_map: card_type_map[name]=call('op.library.card.type','create',[vals])
student_partner={int(r['id']):r['partner_id'][0] for r in call('op.student','search_read',[[('gr_no','like',P+'STU%')]],{'fields':['partner_id','gr_no'],'limit':1000})}
student_source_by_id={int(r['id']):r for r in students}
student_card_map={}
for sid,r in student_source_by_id.items():
    student_id=student_map[P+'STU%04d'%sid]
    card=call('op.student','read',[[student_id],['library_card_id']])[0].get('library_card_id')
    if card: card_id=card[0]
    else:
        card_id=call('op.library.card','create',[{'partner_id':student_partner[student_id],
          'library_card_type_id':card_type_map[P+'CARD-STUDENT'],'issue_date':'2025-01-01',
          'type':'student','student_id':student_id}])
    student_card_map[sid]=card_id
media_move_ids=call('op.media.movement','search',[[('media_unit_id','in',[unit_map[loan_unit_keys[int(r['id'])]] for r in loans])]])
move_unit_ids=set()
if media_move_ids:
    existing_moves=call('op.media.movement','search_read',[[('id','in',media_move_ids)]],{'fields':['media_unit_id'],'limit':1000})
    move_unit_ids={x['media_unit_id'][0] for x in existing_moves if x.get('media_unit_id')}
move_vals=[]
for i,loan in enumerate(loans):
    lid=int(loan['id']); student_source=(i%len(students)+1); sid=student_source
    st_id=student_map[P+'STU%04d'%sid]; unit_id=unit_map[loan_unit_keys[lid]]
    if unit_id in move_unit_ids: continue
    returned=bool(loan.get('return_date'))
    vals={'media_id':media_map[P+'BOOK%04d'%int(loan['book_id'])],
      'media_unit_id':unit_id,'type':'student','student_id':st_id,
      'library_card_id':student_card_map[sid],'partner_id':student_partner[st_id],
      'issued_date':loan['loan_date'],'return_date':loan['due_date'],
      'actual_return_date':loan['return_date'] or False,
      'state':'return_done' if returned else 'issue'}
    move_vals.append(vals);move_unit_ids.add(unit_id)
if move_vals: call('op.media.movement','create',[move_vals])

# Sample tuition/fee invoices as drafts, using the configured Sales journal and receivables.
invoices=rows('invoices'); invoice_items=rows('invoice_items'); fee_types={int(r['id']):r['name'] for r in rows('fee_types')}
items_by_invoice={}
for line in invoice_items: items_by_invoice.setdefault(int(line['invoice_id']),[]).append(line)
existing_invoices=call('account.move','search_read',[[('ref','like',P+'INV%')]],{'fields':['ref'],'limit':1000})
invoice_map={r['ref']:r['id'] for r in existing_invoices}
source_student_enrollment={}
for e in enrollments: source_student_enrollment.setdefault(int(e['student_id']),e)
invoice_vals=[]
for r in invoices:
    iid=int(r['id']); ref=P+'INV%04d'%iid
    if ref in invoice_map: continue
    student_source_id=int(r['student_id']); st_id=student_map[P+'STU%04d'%student_source_id]
    partner=student_partner[st_id]
    cmds=[]
    for line in items_by_invoice.get(iid,[]):
        desc=fee_types.get(int(line['fee_type_id']),'Student fee')
        cmds.append((0,0,{'name':'[Sample] '+desc,'account_id':26,'quantity':1.0,
          'price_unit':float(line['amount']),'tax_ids':[(6,0,[])]}))
    if not cmds:
        cmds=[(0,0,{'name':'[Sample] Tuition fee','account_id':26,'quantity':1.0,
          'price_unit':float(r['total_amount']),'tax_ids':[(6,0,[])]})]
    invoice_vals.append({'move_type':'out_invoice','journal_id':1,'company_id':1,'currency_id':1,
      'partner_id':partner,'invoice_date':r['issue_date'],'invoice_date_due':r['due_date'],
      'date':r['issue_date'],'ref':ref,'auto_post':'no','invoice_line_ids':cmds})
if invoice_vals:
    made=call('account.move','create',[invoice_vals]); made=[made] if isinstance(made,int) else made
    # The created records are draft customer invoices; map by stable ref for fee details.
    refs=[P+'INV%04d'%int(r['id']) for r in invoices if P+'INV%04d'%int(r['id']) not in invoice_map]
    invoice_map.update({ref:mid for ref,mid in zip(refs,made)})
# Link each draft invoice into the OpenEduCat Fees screens.
existing_fee_details=call('op.student.fees.details','search_read',[[('invoice_id','in',list(invoice_map.values()))]],{'fields':['invoice_id'],'limit':2000})
fee_invoice_ids={x['invoice_id'][0] for x in existing_fee_details if x.get('invoice_id')}
fee_vals=[]
for r in invoices:
    iid=int(r['id']); move_id=invoice_map.get(P+'INV%04d'%iid)
    if not move_id or move_id in fee_invoice_ids: continue
    sid=int(r['student_id']); enr=source_student_enrollment.get(sid); detail={'student_id':student_map[P+'STU%04d'%sid],
      'invoice_id':move_id,'amount':float(r['total_amount']),'date':r['issue_date'],'state':'invoice'}
    if enr:
        sec=sections[int(enr['section_id'])]
        detail.update({'course_id':course_map[P+'C%04d'%int(sec['course_id'])],
          'batch_id':batch_map[P+'B%04d'%int(sec['id'])]})
    fee_vals.append(detail);fee_invoice_ids.add(move_id)
if fee_vals: call('op.student.fees.details','create',[fee_vals])

# Public website pages using QWeb views; only sample catalog content is published.
website=call('website','search',[[('domain','in',['localhost','localhost:8069'])]],{})
if not website: website=call('website','search',[[]],{})
website_id=website[0] if website else False
def page_content(title,rows_html):
    return ('<t t-name="openeducat_erp.sample_'+title.lower().replace(' ','_')+'">'
      '<t t-call="website.layout"><div id="wrap" class="oe_structure">'
      '<section class="s_title"><div class="container"><h1>'+html.escape(title)+'</h1>'
      '<p>Sample catalog content from the University Sample Database (CC0).</p></div></section>'
      '<section class="s_text_block"><div class="container"><table class="table table-striped"><tbody>'+rows_html+
      '</tbody></table></div></section></div></t></t>')
def ensure_page(key,url,title,body):
    view_key='openeducat_erp.'+key
    view_ids=call('ir.ui.view','search',[[('key','=',view_key)]])
    viewvals={'name':'[Sample] '+title,'key':view_key,'type':'qweb','mode':'primary','priority':30,
      'arch_db':body,'website_id':website_id or False}
    view_id=view_ids[0] if view_ids else call('ir.ui.view','create',[viewvals])
    if view_ids: call('ir.ui.view','write',[[view_id],{'arch_db':body,'name':'[Sample] '+title}])
    pages=call('website.page','search',[[('url','=',url)]])
    pagevals={'url':url,'view_id':view_id,'name':title,'priority':30,'mode':'primary','is_published':True,'website_id':website_id or False}
    if pages: call('website.page','write',[[pages[0]],pagevals])
    else: call('website.page','create',[pagevals])
course_rows=''.join('<tr><td>'+html.escape(r['code'])+'</td><td>'+html.escape(r['title'])+'</td></tr>' for r in courses[:30])
book_rows=''.join('<tr><td>'+html.escape(r['title'])+'</td><td>'+html.escape(r['author'])+'</td></tr>' for r in books[:30])
ensure_page('sample_courses','/sample-courses','Sample Courses',page_content('Sample Courses',course_rows))
ensure_page('sample_library','/sample-library','Sample Library',page_content('Sample Library',book_rows))

print('HR employees:',call('hr.employee','search_count',[[('work_contact_id.email','like','usample.person%@sample.invalid')]]))
print('Timetable sessions:',call('op.session','search_count',[[('start_datetime','>=','2025-09-01 00:00:00'),('start_datetime','<=','2025-09-30 23:59:59'),('batch_id','in',batch_ids)]]))
print('Attendance registers:',call('op.attendance.register','search_count',[[('code','like',P+'AR%')]]))
print('Attendance sheets:',call('op.attendance.sheet','search_count',[[('register_id.code','like',P+'AR%')]]))
print('Attendance lines:',call('op.attendance.line','search_count',[[('attendance_id.register_id.code','like',P+'AR%')]]))
print('Library titles:',call('op.media','search_count',[[('internal_code','like',P+'BOOK%')]]))
print('Library loans:',call('op.media.movement','search_count',[[('media_unit_id.name','like',P+'UNIT-L%')]]))
print('Draft invoices:',call('account.move','search_count',[[('ref','like',P+'INV%'),('move_type','=','out_invoice'),('state','=','draft')]]))
print('Website pages:',call('website.page','search_count',[[('url','in',['/sample-courses','/sample-library'])]]))



