# Makefile for project-user-recon

install:
	python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

recon-dryrun:
	python -m src.recon.cli recon-dryrun --csv-dir out

apply-deprovision:
	python -m src.recon.cli apply-deprovision --execute --csv-dir out

apply-scim-onboard:
	python -m src.recon.cli apply-scim-onboard --okta-group-id $$OKTA_SCIM_GROUP_ID --execute

reprovision:
	python -m src.recon.cli reprovision --email $$EMAIL --okta-group-id $$OKTA_SCIM_GROUP_ID
