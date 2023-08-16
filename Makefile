HELL=/bin/bash
release: check-git-status set-version push-git-tag deploy

check-git-status:
	@if [[ `git status --porcelain` ]]; then echo "There are unhandled changes! Commit or stash any changes first!"; false; fi

set-version:
ifndef VERSION
	@echo "Missing argument: VERSION" && false;
endif
	@echo $(VERSION) > VERSION
	@poetry run set-version

push-git-tag:
ifndef VERSION
	@echo "Missing argument: VERSION" && false;
endif
	@git add . && \
	git commit -m 'chore: Bump version' && \
	git pull --rebase && \
	git tag v$(VERSION) && \
	git push && git push --tags

build:
	@poetry build

deploy: build
	@poetry publish