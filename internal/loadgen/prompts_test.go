package loadgen

import (
	"strings"
	"testing"
)

func TestPromptsAreDeterministic(t *testing.T) {
	a := PromptFor(Buckets["short"], 42, 3)
	b := PromptFor(Buckets["short"], 42, 3)
	if a != b {
		t.Error("same seed and index gave different prompts")
	}
	if PromptFor(Buckets["short"], 42, 4) == a {
		t.Error("different index gave the same prompt")
	}
}

func TestPromptsShareABucketPrefixButDifferInTheTail(t *testing.T) {
	a := PromptFor(Buckets["medium"], 1, 0)
	b := PromptFor(Buckets["medium"], 1, 1)
	shared := len(commonPrefix(a, b))
	if shared < len(a)/3 {
		t.Errorf("shared prefix %d chars is too short for prefix caching to be measurable", shared)
	}
	if a == b {
		t.Error("prompts are identical, so the cache would serve everything")
	}
}

func TestBucketLengthsOrder(t *testing.T) {
	short := len(strings.Fields(PromptFor(Buckets["short"], 7, 0)))
	medium := len(strings.Fields(PromptFor(Buckets["medium"], 7, 0)))
	long := len(strings.Fields(PromptFor(Buckets["long"], 7, 0)))
	if !(short < medium && medium < long) {
		t.Errorf("bucket word counts out of order: %d %d %d", short, medium, long)
	}
	if got, want := short, Buckets["short"].TargetTokens; got < want/2 || got > want*2 {
		t.Errorf("short bucket produced %d words, target is %d tokens", got, want)
	}
}

func commonPrefix(a, b string) string {
	n := min(len(a), len(b))
	i := 0
	for i < n && a[i] == b[i] {
		i++
	}
	return a[:i]
}
