package loadgen

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func streamingServer(t *testing.T, tokens int) (*httptest.Server, *int64, *int64) {
	t.Helper()
	var total, peak int64
	var mu sync.Mutex
	inFlight := int64(0)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt64(&total, 1)
		cur := atomic.AddInt64(&inFlight, 1)
		mu.Lock()
		if cur > peak {
			peak = cur
		}
		mu.Unlock()
		defer atomic.AddInt64(&inFlight, -1)

		fl := w.(http.Flusher)
		time.Sleep(20 * time.Millisecond)
		for i := 0; i < tokens; i++ {
			fmt.Fprintf(w, "data: {\"choices\":[{\"text\":\" t%d\"}]}\n\n", i)
			fl.Flush()
		}
		fmt.Fprintf(w, "data: {\"choices\":[],\"usage\":{\"prompt_tokens\":11,\"completion_tokens\":%d}}\n\n", tokens)
		fl.Flush()
		fmt.Fprint(w, "data: [DONE]\n\n")
	}))
	return srv, &total, &peak
}

func TestRunExcludesWarmupAndHoldsConcurrency(t *testing.T) {
	srv, total, peak := streamingServer(t, 4)
	defer srv.Close()
	dir := t.TempDir()

	s, err := Run(context.Background(), Config{
		BaseURL: srv.URL, Model: "m", Engine: "fake", Bucket: "short", OutDir: dir,
		Concurrency: 4, Requests: 16, Warmup: 4, MaxTokens: 4, Seed: 1,
		PrefixCaching: true, Timeout: 30 * time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	if got := atomic.LoadInt64(total); got != 20 {
		t.Errorf("server saw %d requests, want 16 measured plus 4 warmup", got)
	}
	if s.Requests != 16 || s.Errors != 0 {
		t.Errorf("summary counted %d requests, %d errors", s.Requests, s.Errors)
	}
	if s.OutputTokens != 64 {
		t.Errorf("output tokens %d, want 16 requests x 4 tokens", s.OutputTokens)
	}
	if p := atomic.LoadInt64(peak); p > 4 {
		t.Errorf("peak in-flight %d exceeded the configured concurrency", p)
	}
	if s.TTFTms.Count != 16 || s.TTFTms.P50 < 15 {
		t.Errorf("TTFT summary looks wrong: %+v", s.TTFTms)
	}

	lines := readJSONL(t, filepath.Join(dir, "fake-short-c4.jsonl"))
	if len(lines) != 16 {
		t.Errorf("wrote %d records, want 16", len(lines))
	}
}

func TestRunReportsErrorsWithoutInventingNumbers(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()

	_, err := Run(context.Background(), Config{
		BaseURL: srv.URL, Model: "m", Engine: "fake", Bucket: "short", OutDir: t.TempDir(),
		Concurrency: 2, Requests: 4, Warmup: 0, MaxTokens: 4, Timeout: 5 * time.Second,
	})
	if err == nil {
		t.Fatal("a run where every request failed should return an error")
	}
}

func readJSONL(t *testing.T, path string) []Record {
	t.Helper()
	f, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var out []Record
	dec := json.NewDecoder(f)
	for dec.More() {
		var r Record
		if err := dec.Decode(&r); err != nil {
			t.Fatal(err)
		}
		out = append(out, r)
	}
	return out
}
