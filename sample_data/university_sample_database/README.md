# University sample database import

Source: [University sample database](https://databasesample.com/datasets/university-sample-database)
License stated by the source: CC0 1.0 Public Domain.

This folder contains the source CSV tables used by `import_university_sample.py`.
The importer creates sample departments, courses and subjects, faculty, students,
academic years/terms, batches, enrollments, exam sessions, exams, results,
assignments and assignment submissions in the `openeducat` database. It also
creates five sample admission registers and 30 sample applications using the
imported students. The source database does not include admissions, so those
records are generated for testing. The importer can be rerun without creating
duplicates.

Imported source rows: 14 departments, 600 courses, 10 instructors, 50 students,
1,000 enrollments, 80 exams, 300 exam results, 120 assignments and 400 assignment
submissions. Three exams have no score rows in the source dataset. Sample contact
emails are replaced with non-deliverable `.invalid` addresses.

The dataset contains generated sample data; do not treat names/contact details as
real institutional records.

## Additional sample data

`import_remaining_sample_data.py` loads the public schedule, library, and invoice
tables and creates linked OpenEduCat records. It is safe to rerun.

- 10 sample faculty members linked to HR employee records.
- 60 timetable sessions, 10 attendance registers, 30 attendance sheets, and
  1,038 attendance lines.
- 2,000 library books, 2,100 book units, 50 student library cards, and 100
  circulation records.
- 100 customer invoices with matching OpenEduCat fee records. Invoices are left
  in draft so they can be reviewed before posting.
- 2 website pages: `/sample-courses` and `/sample-library`.
- The 600 sample courses and subjects, 5 admissions registers, and 30 admission
  applications are loaded by `import_university_sample.py`.

Both importers use the public dataset source described above; generated
attendance, admissions, and website content are for development/demo use. All
sample email addresses use the non-deliverable `.invalid` domain.

`import_sis_reference_data.py` fills SIS reference data that the public dataset
does not provide: 5 programs across 4 program levels, 3 academic terms, 3 fee
plans with 8 installment lines, 12 classrooms with 36 facility assignments,
6 facilities, 5 student categories, and 4 parent relationship types. It also
creates 50 sample guardian records linked to the 50 imported students and assigns
each student a category. Guardian contacts use `.invalid` email addresses and
synthetic phone numbers. The script can be rerun without duplicating these rows.

`import_elearning_sample_data.py` creates 4 published eLearning courses, 12
article lessons, 4 quizzes with 8 questions and 22 answer choices, and 104
attendee enrollments for the imported students. The course pages are available
under `/slides/` in the local Odoo website. Lesson and quiz material is generated
for demonstration and can be edited in eLearning.

`load_online_elearning_sources.py` loads two public learning sources:

- **OULAD:** the official 44.7 MB archive is saved at
  `sample_data/oulad/anonymisedData.zip`. The importer creates 22 published
  module-presentation eLearning courses with 66 lessons summarizing module
  lengths, assessment types, and VLE activity profiles. It links the 32,593
  existing anonymized SIS course registrations to those eLearning courses. The
  activity profiles summarize recorded VLE clicks by activity type. OULAD is
  released under CC BY 4.0; attribute The Open University and cite Kuzilek,
  Hlosta, and Zdrahal (2017), DOI `10.1038/sdata.2017.171`.
- **OpenLearn:** one published course with eight lesson pages links to the
  official Open University course sections. The lesson text is a short
  orientation summary, with attribution and canonical links; it does not copy
  the full OpenLearn course. OpenLearn materials are for non-commercial use
  under applicable Creative Commons terms, and individual acknowledgements may
  impose special restrictions. Review those terms before reusing the materials
  beyond this local demo.

The OpenLearn download endpoint returned HTTP 403 during import, so those lesson
pages link to the original OpenLearn site. The OULAD dataset is data about
learners and VLE activity, not course lesson text.
