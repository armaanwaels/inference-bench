package openai

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Usage is the token accounting an engine reports on the final stream frame.
type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
}

// Chunk is one parsed server-sent event from a streaming completion.
type Chunk struct {
	Text  string
	Usage *Usage
}

type wireChunk struct {
	Choices []struct {
		Text  string `json:"text"`
		Delta struct {
			Content string `json:"content"`
		} `json:"delta"`
	} `json:"choices"`
	Usage *Usage `json:"usage"`
}

// ParseLine parses one SSE line. The bool reports whether the stream is finished.
func ParseLine(line string) (Chunk, bool, error) {
	line = strings.TrimSpace(line)
	if line == "" || strings.HasPrefix(line, ":") {
		return Chunk{}, false, nil
	}
	payload, found := strings.CutPrefix(line, "data:")
	if !found {
		return Chunk{}, false, fmt.Errorf("line is not an SSE data frame: %q", truncate(line))
	}
	payload = strings.TrimSpace(payload)
	if payload == "[DONE]" {
		return Chunk{}, true, nil
	}
	var w wireChunk
	if err := json.Unmarshal([]byte(payload), &w); err != nil {
		return Chunk{}, false, fmt.Errorf("bad JSON in data frame: %w", err)
	}
	c := Chunk{Usage: w.Usage}
	for _, ch := range w.Choices {
		c.Text += ch.Text + ch.Delta.Content
	}
	return c, false, nil
}

// Request is one completion call.
type Request struct {
	Model     string
	Prompt    string
	MaxTokens int
	IgnoreEOS bool
}

// Result is the client-side measurement of one completion call.
type Result struct {
	TTFT             time.Duration
	Total            time.Duration
	PromptTokens     int
	CompletionTokens int
}

// Client calls an OpenAI-compatible /v1/completions endpoint with streaming on.
type Client struct {
	BaseURL string
	HTTP    *http.Client
}

// Stream sends one request and measures time to first token and total time at the client.
func (c *Client) Stream(ctx context.Context, r Request) (Result, error) {
	body, err := json.Marshal(map[string]any{
		"model":          r.Model,
		"prompt":         r.Prompt,
		"max_tokens":     r.MaxTokens,
		"temperature":    0,
		"stream":         true,
		"ignore_eos":     r.IgnoreEOS,
		"stream_options": map[string]any{"include_usage": true},
	})
	if err != nil {
		return Result{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.BaseURL+"/v1/completions", bytes.NewReader(body))
	if err != nil {
		return Result{}, err
	}
	req.Header.Set("Content-Type", "application/json")

	start := time.Now()
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return Result{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		msg, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return Result{}, fmt.Errorf("http %d: %s", resp.StatusCode, bytes.TrimSpace(msg))
	}

	var res Result
	sawText := false
	sc := bufio.NewScanner(resp.Body)
	sc.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	for sc.Scan() {
		chunk, done, err := ParseLine(sc.Text())
		if err != nil {
			return Result{}, err
		}
		if done {
			break
		}
		if chunk.Text != "" && !sawText {
			res.TTFT = time.Since(start)
			sawText = true
		}
		if chunk.Usage != nil {
			res.PromptTokens = chunk.Usage.PromptTokens
			res.CompletionTokens = chunk.Usage.CompletionTokens
		}
	}
	if err := sc.Err(); err != nil {
		return Result{}, err
	}
	res.Total = time.Since(start)
	if !sawText {
		return Result{}, fmt.Errorf("stream carried no text")
	}
	if res.CompletionTokens == 0 {
		return Result{}, fmt.Errorf("engine reported no completion_tokens; refusing to guess output length")
	}
	return res, nil
}

func truncate(s string) string {
	if len(s) > 80 {
		return s[:80] + "..."
	}
	return s
}
