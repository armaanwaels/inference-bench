package loadgen

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/armaanwaels/inference-bench/internal/openai"
	"github.com/armaanwaels/inference-bench/internal/stats"
)

// Config is one cell of the run matrix: one engine, one concurrency, one prompt bucket.
type Config struct {
	BaseURL       string
	Model         string
	Engine        string
	Bucket        string
	GPU           string
	Dtype         string
	Commit        string
	OutDir        string
	Concurrency   int
	Requests      int
	Warmup        int
	MaxTokens     int
	Seed          int
	PrefixCaching bool
	Timeout       time.Duration
}

// Record is one measured request.
type Record struct {
	Index            int     `json:"index"`
	Engine           string  `json:"engine"`
	Bucket           string  `json:"bucket"`
	Concurrency      int     `json:"concurrency"`
	TTFTms           float64 `json:"ttft_ms"`
	LatencyMs        float64 `json:"latency_ms"`
	PromptTokens     int     `json:"prompt_tokens"`
	CompletionTokens int     `json:"completion_tokens"`
	Error            string  `json:"error,omitempty"`
}

// Summary is the aggregate for one cell, written next to the per-request records.
type Summary struct {
	Engine            string        `json:"engine"`
	Model             string        `json:"model"`
	Dtype             string        `json:"dtype"`
	GPU               string        `json:"gpu"`
	GPUMemoryMiB      int           `json:"gpu_memory_mib"`
	Bucket            string        `json:"bucket"`
	Concurrency       int           `json:"concurrency"`
	PrefixCaching     bool          `json:"prefix_caching"`
	Requests          int           `json:"requests"`
	Errors            int           `json:"errors"`
	MaxTokens         int           `json:"max_tokens"`
	MeanPromptTokens  float64       `json:"mean_prompt_tokens"`
	OutputTokens      int           `json:"output_tokens"`
	WallSeconds       float64       `json:"wall_seconds"`
	OutputTokensPerS  float64       `json:"output_tokens_per_s"`
	RequestsPerS      float64       `json:"requests_per_s"`
	TTFTms            stats.Summary `json:"ttft_ms"`
	LatencyMs         stats.Summary `json:"latency_ms"`
	Commit            string        `json:"commit"`
	TimestampUTC      string        `json:"timestamp_utc"`
	LoadgenConcurrent bool          `json:"closed_loop"`
}

// Run drives one cell and writes <engine>-<bucket>-c<concurrency>.{jsonl,json} into OutDir.
func Run(ctx context.Context, cfg Config) (Summary, error) {
	bucket, ok := Buckets[cfg.Bucket]
	if !ok {
		return Summary{}, fmt.Errorf("unknown bucket %q", cfg.Bucket)
	}
	client := &openai.Client{
		BaseURL: cfg.BaseURL,
		HTTP:    &http.Client{Timeout: cfg.Timeout},
	}

	// Warmup absorbs weight loading, CUDA graph capture and allocator growth.
	warmup := make(chan int, cfg.Warmup)
	for i := 0; i < cfg.Warmup; i++ {
		warmup <- -(i + 1)
	}
	close(warmup)
	drain(ctx, client, cfg, bucket, warmup, nil)

	jobs := make(chan int, cfg.Requests)
	for i := 0; i < cfg.Requests; i++ {
		jobs <- i
	}
	close(jobs)

	records := make([]Record, 0, cfg.Requests)
	var mu sync.Mutex
	start := time.Now()
	drain(ctx, client, cfg, bucket, jobs, func(r Record) {
		mu.Lock()
		records = append(records, r)
		mu.Unlock()
	})
	wall := time.Since(start).Seconds()

	return summarize(cfg, bucket, records, wall)
}

func drain(ctx context.Context, c *openai.Client, cfg Config, b Bucket, jobs <-chan int, sink func(Record)) {
	var wg sync.WaitGroup
	for w := 0; w < cfg.Concurrency; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				res, err := c.Stream(ctx, openai.Request{
					Model:     cfg.Model,
					Prompt:    PromptFor(b, cfg.Seed, i),
					MaxTokens: cfg.MaxTokens,
					IgnoreEOS: true,
				})
				if sink == nil {
					continue
				}
				rec := Record{
					Index: i, Engine: cfg.Engine, Bucket: cfg.Bucket, Concurrency: cfg.Concurrency,
				}
				if err != nil {
					rec.Error = err.Error()
				} else {
					rec.TTFTms = float64(res.TTFT.Microseconds()) / 1000
					rec.LatencyMs = float64(res.Total.Microseconds()) / 1000
					rec.PromptTokens = res.PromptTokens
					rec.CompletionTokens = res.CompletionTokens
				}
				sink(rec)
			}
		}()
	}
	wg.Wait()
}

func summarize(cfg Config, b Bucket, records []Record, wall float64) (Summary, error) {
	var ttfts, lats []float64
	errors, outTokens, promptTokens := 0, 0, 0
	for _, r := range records {
		if r.Error != "" {
			errors++
			continue
		}
		ttfts = append(ttfts, r.TTFTms)
		lats = append(lats, r.LatencyMs)
		outTokens += r.CompletionTokens
		promptTokens += r.PromptTokens
	}
	ok := len(records) - errors
	if ok == 0 {
		return Summary{}, fmt.Errorf("all %d requests failed; first error: %s", len(records), firstError(records))
	}
	ttftSummary, _ := stats.Describe(ttfts)
	latSummary, _ := stats.Describe(lats)
	s := Summary{
		Engine: cfg.Engine, Model: cfg.Model, Dtype: cfg.Dtype, GPU: cfg.GPU,
		GPUMemoryMiB: gpuMemoryMiB(), Bucket: cfg.Bucket, Concurrency: cfg.Concurrency,
		PrefixCaching: cfg.PrefixCaching, Requests: len(records), Errors: errors,
		MaxTokens: cfg.MaxTokens, MeanPromptTokens: float64(promptTokens) / float64(ok),
		OutputTokens: outTokens, WallSeconds: wall,
		OutputTokensPerS: float64(outTokens) / wall, RequestsPerS: float64(ok) / wall,
		TTFTms: ttftSummary, LatencyMs: latSummary, Commit: cfg.Commit,
		TimestampUTC: time.Now().UTC().Format(time.RFC3339), LoadgenConcurrent: true,
	}
	return s, write(cfg, records, s)
}

func firstError(records []Record) string {
	for _, r := range records {
		if r.Error != "" {
			return r.Error
		}
	}
	return ""
}

func write(cfg Config, records []Record, s Summary) error {
	if cfg.OutDir == "" {
		return nil
	}
	if err := os.MkdirAll(cfg.OutDir, 0o755); err != nil {
		return err
	}
	stem := fmt.Sprintf("%s-%s-c%d", cfg.Engine, cfg.Bucket, cfg.Concurrency)
	if !cfg.PrefixCaching {
		stem += "-nocache"
	}
	f, err := os.Create(filepath.Join(cfg.OutDir, stem+".jsonl"))
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	for _, r := range records {
		if err := enc.Encode(r); err != nil {
			return err
		}
	}
	blob, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(cfg.OutDir, stem+".json"), append(blob, '\n'), 0o644)
}
