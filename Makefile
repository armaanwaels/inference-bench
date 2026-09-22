.PHONY: loadgen matrix bench report test lint

loadgen:           ## build the load generator for the Modal container
	GOOS=linux GOARCH=amd64 go build -o build/loadgen-linux-amd64 ./cmd/loadgen

matrix:            ## print the run matrix and the cost estimate, spends nothing
	python bench/matrix.py

bench: loadgen     ## run the whole matrix on Modal, then write the report
	modal run bench/modal_app.py --confirm
	$(MAKE) report

report:            ## regenerate results/summary.md and the chart from results/
	python bench/report.py

test:
	go test ./...
	pytest -q

lint:
	go vet ./...
	gofmt -l cmd internal
	ruff check .
	ruff format --check .
