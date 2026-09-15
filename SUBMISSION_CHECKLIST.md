# Submission checklist

Complete this list against the exact commit that will be emailed for review.

## One manual value still required

- [ ] Replace the `Time spent` TODO in `README.md` with actual hours and minutes.

## Clean-clone behavior

- [ ] Run `./reset.sh` and confirm it removes only this project's resources.
- [ ] Run `./dev.sh` and wait for the full archive import and server startup.
- [ ] Run `./verify.sh` unchanged in another terminal.
- [ ] Confirm [http://localhost:3000](http://localhost:3000) loads.
- [ ] Run the full 34-test suite:

```bash
docker compose build app
docker compose run --rm --entrypoint /app/.venv/bin/python app manage.py test
```

- [ ] Run `docker compose down`, then `./dev.sh`; confirm the log says the legacy
  archive is already imported and user changes remain.
- [ ] Confirm protected inputs are unchanged:

```bash
git diff -- ASSIGNMENT.md verify.sh data docs/environment.md docs/image-policy.md
```

## Demo check

- [ ] Follow [docs/DEMO.md](docs/DEMO.md) once after a reset.
- [ ] Confirm `OP011026` demonstrates missing area and rerun comparison.
- [ ] Confirm `OP000005` demonstrates the height conflict.
- [ ] Confirm `OP000230` demonstrates a complete enquiry.
- [ ] Reset again after rehearsal so the interview starts from known data.

## Repository check

- [ ] Review `git status` and commit all intended Phase 8 files.
- [ ] Push the final commit before composing the email.
- [ ] Open the repository in a signed-out/private browser window and confirm it is
  publicly accessible.
- [ ] Copy the exact full commit hash:

```bash
git rev-parse HEAD
```

- [ ] Do not push later changes to the submitted commit without sending a new
  hash.

## Submission email

Use the exact recipients, subject format and field labels:

```text
To: giuseppe@2clicksolutions.com
Cc: alberto.canci@playgroundaps.it, info@nicolopadovan.com
Subject: Assignment submission - [First name] [Surname]

First name: [First name]
Surname: [Surname]
Email: [Your contact email]
Repository URL: [Public repository URL]
Commit hash: [Full commit hash to review]
Time spent: [Hours and minutes]
```

- [ ] Confirm names, email, public repository URL, full hash and time spent.
- [ ] Send the email before the deadline. Pushing code alone does not count.
- [ ] Do not attach code or use a file-sharing link.
- [ ] Keep the public repository available until the hiring process ends.
