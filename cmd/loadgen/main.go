package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/armaanwaels/inference-bench/internal/loadgen"
)

func main() {
	cfg := loadgen.Config{}
	flag.StringVar(&cfg.BaseURL, "base-url", "http://127.0.0.1:8000", "engine base URL")
	flag.StringVar(&cfg.Model, "model", "", "model name the engine serves")
	flag.StringVar(&cfg.Engine, "engine", "", "engine label for the output files")
	flag.StringVar(&cfg.Bucket, "bucket", "short", "prompt bucket: short, medium or long")
	flag.StringVar(&cfg.GPU, "gpu", "", "GPU name recorded in the summary")
	flag.StringVar(&cfg.Dtype, "dtype", "bfloat16", "dtype recorded in the summary")
	flag.StringVar(&cfg.Commit, "commit", "", "git commit recorded in the summary")
	flag.StringVar(&cfg.OutDir, "out", "results", "directory for the JSONL and summary")
	flag.IntVar(&cfg.Concurrency, "concurrency", 1, "requests in flight")
	flag.IntVar(&cfg.Requests, "requests", 32, "measured requests")
	flag.IntVar(&cfg.Warmup, "warmup", 4, "warmup requests, excluded from the stats")
	flag.IntVar(&cfg.MaxTokens, "max-tokens", 128, "output tokens per request")
	flag.IntVar(&cfg.Seed, "seed", 1, "prompt seed")
	flag.BoolVar(&cfg.PrefixCaching, "prefix-caching", true, "label only: what the engine was started with")
	timeout := flag.Duration("timeout", 10*time.Minute, "per-request timeout")
	flag.Parse()

	cfg.Timeout = *timeout
	if cfg.Model == "" || cfg.Engine == "" {
		fmt.Fprintln(os.Stderr, "-model and -engine are required")
		os.Exit(2)
	}

	summary, err := loadgen.Run(context.Background(), cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, "run failed:", err)
		os.Exit(1)
	}
	out, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(string(out))
	if summary.Errors > 0 {
		os.Exit(3)
	}
}
