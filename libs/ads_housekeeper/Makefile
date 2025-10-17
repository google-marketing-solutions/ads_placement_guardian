SHELL=/bin/bash
PYTHON=`which python`

.PHONY: build
build:
	DOCKER_BUILDKIT=1 docker build -t ads_housekeeper .

force_build:
	DOCKER_BUILDKIT=1 docker build -t ads_housekeeper --no-cache .

clean:
	@echo "Removing the build/ dist/ and *.egg-info/ directories"
	@rm -rf dist *.egg-info

upload:
	@echo "Uploading built package to PyPI"
	@${PYTHON} `which twine` upload dist/*

bundle:
	@echo "Bundling the code"; echo
	@${PYTHON} setup.py sdist

upload_pypi: | clean bundle upload
