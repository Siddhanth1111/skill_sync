# Gold set

This folder is empty on purpose. The plan needs 150 or more resume and requirement pairs graded by **two humans**, and
nothing here pretends otherwise. Do not fill it with model-generated labels and call it a gold set.

**Format** (`pairs.jsonl`, one object per line):

```json
{"id": "p001", "job": "j1", "requirement": "Python", "resume": "Wrote automation scripts in Perl", "grade": 0}
```

`grade`: 0 = the resume does not show the requirement, 1 = partly shown, 2 = clearly shown.

**Rubric** (write it down before the pilot round, adjudicate disagreements, report kappa between the two annotators):

- 2: a specific bullet or sentence states the skill or an obvious paraphrase, in work or a project.
- 1: a related tool, a named technique of the skill, a skills-list mention only, or evidence too thin to be sure.
- 0: nothing in the text supports it, or only a different tool (Perl is not Python, RabbitMQ is not Kafka).

**Rules:** synthetic or consented resumes only; the files never go to version control (`*.jsonl` here is ignored);
split development and test by **job**, and open the test split once. Seed pairs can come from the product itself:
`python -m app.cli export-gold seeds.jsonl` writes every "wrong evidence" verdict reviewers have recorded.

**Run:** `python -m eval.benchmark eval/gold/pairs.jsonl --out eval/results/v2.json`
