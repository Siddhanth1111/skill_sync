"""Review items C1, C2, A9, A7, A8: resume units with context, wider headings, no contact text, skill years."""
from app.services.chunking import chunk_resume, heading_section, inline_heading, split_sections
from app.services.skillgraph import link_skills, undated_roles

RESUME = """Priya Nair
priya@example.com | +91 98765 43210 | Bengaluru

PROFESSIONAL PROFILE
Backend developer with seven years of experience building scalable data services and APIs.

CAREER DETAILS
Backend Developer - Acme   Jan 2021 - Dec 2023
• Tuned slow SQL using execution plans
  and indexes on PostgreSQL
• Automated builds and deployments with Jenkins
Intern, Beta Labs   Jun 2019 - Aug 2019
• Wrote Perl scripts

Education: B.Tech in Computer Science, 2017
Technical Proficiency: Python, SQL, Docker
Hobbies: chess
"""


def test_c1_common_and_inline_headings_are_recognised():
    assert heading_section("PROFESSIONAL PROFILE") == "summary"
    assert heading_section("CAREER DETAILS") == "experience"
    assert heading_section("Technical Proficency") == "skills"  # typo, fuzzy match
    assert heading_section("Experienced engineer") is None      # not a heading
    assert inline_heading("Education: B.Tech in CS, 2017") == ("education", "B.Tech in CS, 2017")
    secs = [s for s, _ in split_sections(RESUME)]
    assert secs == ["header", "summary", "experience", "education", "skills", "interests"]


def test_c2_units_are_single_bullets_with_the_role_as_context():
    units = chunk_resume(RESUME)
    exp = [u for u in units if u.section == "experience"]
    assert len(exp) == 3
    assert exp[0].text == "Tuned slow SQL using execution plans\nand indexes on PostgreSQL"  # wrapped bullet joined
    assert "Backend Developer - Acme" in exp[0].context and exp[0].start == "Jan 2021" and exp[0].end == "Dec 2023"
    assert "Intern, Beta Labs" in exp[2].context
    assert exp[0].embed_text.startswith(exp[0].context)
    for u in units:  # every unit is still a substring of the resume, so quotes verify
        assert " ".join(u.text.split()) in " ".join(RESUME.split())


def test_a9_contact_name_and_personal_sections_are_not_indexed():
    text = " ".join(u.text for u in chunk_resume(RESUME))
    assert "priya@example.com" not in text and "98765" not in text and "Bengaluru" not in text
    assert "Priya Nair" not in text and "chess" not in text


def test_a7_years_per_skill_come_from_dated_roles_with_overlaps_merged():
    units = chunk_resume(RESUME)
    links, years = link_skills(units)
    assert years["postgresql"] == 3.0 and years["sql"] == 3.0       # Jan 2021 - Dec 2023
    assert years["ci/cd"] == 3.0 and years.get("perl", 0) < 1       # the Perl internship was 3 months
    assert "python" not in years or years["python"] == 0            # listed in a skills line only: no dated years
    assert links["sql"]


def test_a8_undated_roles_are_counted_so_the_ui_can_flag_them():
    text = "EXPERIENCE\nData Analyst, Acme\n- Built dashboards in Tableau\n"
    assert undated_roles(chunk_resume(text)) == 1
    assert undated_roles(chunk_resume(RESUME)) == 0


def test_resume_without_any_heading_is_still_indexed():
    units = chunk_resume("Short line\nBuilt Python services for a bank over three years.\nRan Kafka jobs daily.")
    assert len(units) >= 2 and all(u.section == "header" for u in units)
