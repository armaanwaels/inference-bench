package loadgen

import (
	"fmt"
	"hash/fnv"
	"math/rand"
	"strings"
)

// Bucket is a prompt-length class. Lengths are targets in tokens, not guarantees.
type Bucket struct {
	Name         string
	TargetTokens int
}

var Buckets = map[string]Bucket{
	"short":  {"short", 128},
	"medium": {"medium", 512},
	"long":   {"long", 2048},
}

// vocab is deliberately plain: common short words cost about one token each in
// the tokenizers these engines use, so word count tracks token count closely.
var vocab = strings.Fields(`
time year people way day man thing woman life child world school state family
student group country problem hand part place case week company system program
question work government number night point home water room mother area money
story fact month lot right study book eye job word business issue side kind head
house service friend father power hour game line end member law car city name
team minute idea kid body back parent face level office door health person art
war history party result change morning reason research girl guy moment air
teacher force education foot boy age policy process music market sense nation
plan college interest death experience effect use class control care field
development role effort rule report mind service south product value action
`)

// PromptFor builds a deterministic prompt for one request.
// Every prompt starts with a shared per-bucket prefix so prefix caching has something to hit,
// then a unique tail so the engines cannot serve the whole request from cache.
func PromptFor(b Bucket, seed, index int) string {
	const prefixShare = 0.6
	prefixWords := int(float64(b.TargetTokens) * prefixShare)
	tailWords := b.TargetTokens - prefixWords

	var sb strings.Builder
	sb.WriteString(words(bucketSeed(b.Name, seed), prefixWords))
	fmt.Fprintf(&sb, "\n\nRequest %d. ", index)
	sb.WriteString(words(int64(seed*1_000_003+index), tailWords))
	sb.WriteString("\n\nContinue the notes above.\n")
	return sb.String()
}

func bucketSeed(name string, seed int) int64 {
	h := fnv.New64a()
	fmt.Fprintf(h, "%s:%d", name, seed)
	return int64(h.Sum64() & 0x7fffffffffffffff)
}

func words(seed int64, n int) string {
	if n <= 0 {
		return ""
	}
	r := rand.New(rand.NewSource(seed))
	out := make([]string, n)
	for i := range out {
		out[i] = vocab[r.Intn(len(vocab))]
	}
	return strings.Join(out, " ")
}
