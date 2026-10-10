.PHONY: data run report test clean all

data:      ## generate 30 days of messy sample data
	python3 -m pipeline generate --days 30

run:       ## ingest -> transform -> quality checks
	python3 -m pipeline run

report:    ## print business insights from the gold marts
	python3 -m pipeline report

test:      ## run unit + behaviour tests
	python3 -m unittest discover -s tests -v

all: data run report

clean:
	rm -rf data
