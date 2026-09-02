.PHONY: test doctor dry-run

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

doctor:
	PYTHONPATH=src python3 -m host_slot_switch doctor

dry-run:
	PYTHONPATH=src python3 -m host_slot_switch switch laptop --dry-run
