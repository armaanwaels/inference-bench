package openai

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestParseLineTextFrames(t *testing.T) {
	c, done, err := ParseLine(`data: {"choices":[{"text":"hello world"}]}`)
	if err != nil || done || c.Text != "hello world" {
		t.Fatalf("completions frame: %+v done=%v err=%v", c, done, err)
	}
	c, _, err = ParseLine(`data: {"choices":[{"delta":{"content":"chat style"}}]}`)
	if err != nil || c.Text != "chat style" {
		t.Fatalf("chat frame: %+v err=%v", c, err)
	}
}

func TestParseLineMultiTokenChunk(t *testing.T) {
	c, _, err := ParseLine(`data: {"choices":[{"text":" one two three four"}]}`)
	if err != nil || c.Text != " one two three four" {
		t.Fatalf("multi-token chunk: %+v err=%v", c, err)
	}
}

func TestParseLineDoneAndBlank(t *testing.T) {
	if _, done, err := ParseLine("data: [DONE]"); !done || err != nil {
		t.Errorf("[DONE] not recognised: done=%v err=%v", done, err)
	}
	if c, done, err := ParseLine(""); done || err != nil || c.Text != "" {
		t.Errorf("blank line: %+v done=%v err=%v", c, done, err)
	}
	if _, _, err := ParseLine(": keep-alive"); err != nil {
		t.Errorf("comment line: %v", err)
	}
}

func TestParseLineUsageFrame(t *testing.T) {
	c, _, err := ParseLine(`data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":34}}`)
	if err != nil {
		t.Fatal(err)
	}
	if c.Usage == nil || c.Usage.PromptTokens != 12 || c.Usage.CompletionTokens != 34 {
		t.Fatalf("usage frame: %+v", c.Usage)
	}
}

func TestParseLineMalformed(t *testing.T) {
	if _, _, err := ParseLine("data: {not json"); err == nil {
		t.Error("malformed JSON accepted")
	}
	if _, _, err := ParseLine("event: ping"); err == nil {
		t.Error("non-data frame accepted")
	}
}

// fakeServer streams a fixed number of tokens with a delay before the first one.
func fakeServer(t *testing.T, firstTokenDelay time.Duration, tokens int, withUsage bool) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fl, ok := w.(http.Flusher)
		if !ok {
			t.Fatal("test server needs a flusher")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		time.Sleep(firstTokenDelay)
		for i := 0; i < tokens; i++ {
			fmt.Fprintf(w, "data: {\"choices\":[{\"text\":\" tok%d\"}]}\n\n", i)
			fl.Flush()
		}
		if withUsage {
			fmt.Fprintf(w, "data: {\"choices\":[],\"usage\":{\"prompt_tokens\":7,\"completion_tokens\":%d}}\n\n", tokens)
			fl.Flush()
		}
		fmt.Fprint(w, "data: [DONE]\n\n")
	}))
}

func TestStreamMeasuresTTFTAndUsage(t *testing.T) {
	srv := fakeServer(t, 120*time.Millisecond, 5, true)
	defer srv.Close()

	c := &Client{BaseURL: srv.URL, HTTP: srv.Client()}
	res, err := c.Stream(context.Background(), Request{Model: "m", Prompt: "p", MaxTokens: 5})
	if err != nil {
		t.Fatal(err)
	}
	if res.TTFT < 100*time.Millisecond {
		t.Errorf("TTFT %v shorter than the server's own delay", res.TTFT)
	}
	if res.Total < res.TTFT {
		t.Errorf("total %v below TTFT %v", res.Total, res.TTFT)
	}
	if res.CompletionTokens != 5 || res.PromptTokens != 7 {
		t.Errorf("usage not recorded: %+v", res)
	}
}

func TestStreamFailsWhenUsageMissing(t *testing.T) {
	srv := fakeServer(t, 0, 3, false)
	defer srv.Close()

	c := &Client{BaseURL: srv.URL, HTTP: srv.Client()}
	_, err := c.Stream(context.Background(), Request{Model: "m", Prompt: "p", MaxTokens: 3})
	if err == nil || !strings.Contains(err.Error(), "completion_tokens") {
		t.Fatalf("missing usage should fail loudly, got %v", err)
	}
}

func TestStreamSurfacesHTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "model not found", http.StatusNotFound)
	}))
	defer srv.Close()

	c := &Client{BaseURL: srv.URL, HTTP: srv.Client()}
	if _, err := c.Stream(context.Background(), Request{Model: "m"}); err == nil {
		t.Fatal("404 was not surfaced")
	}
}
