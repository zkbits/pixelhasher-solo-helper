solo:
	pipenv run python -m src.solo

check_code:
	-pipenv run flake8 src
	-pipenv run pylint --rcfile setup.cfg src

format_code:
	-pipenv run black src
