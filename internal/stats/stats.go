package stats

import (
	"math"
	"sort"
)

// Summary holds the percentiles and count for one sample set.
type Summary struct {
	Count int     `json:"count"`
	P50   float64 `json:"p50"`
	P95   float64 `json:"p95"`
	P99   float64 `json:"p99"`
	Mean  float64 `json:"mean"`
	Min   float64 `json:"min"`
	Max   float64 `json:"max"`
}

// Percentile returns the nearest-rank percentile of xs for p in [0,100].
// Nearest rank always returns an observed value, so a reported p99 is a request that happened.
func Percentile(xs []float64, p float64) (float64, bool) {
	if len(xs) == 0 || math.IsNaN(p) || p < 0 || p > 100 {
		return 0, false
	}
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	rank := int(math.Ceil(p / 100 * float64(len(s))))
	if rank < 1 {
		rank = 1
	}
	return s[rank-1], true
}

// Describe returns count, percentiles, mean and range for xs.
func Describe(xs []float64) (Summary, bool) {
	if len(xs) == 0 {
		return Summary{}, false
	}
	p50, _ := Percentile(xs, 50)
	p95, _ := Percentile(xs, 95)
	p99, _ := Percentile(xs, 99)
	sum, min, max := 0.0, xs[0], xs[0]
	for _, x := range xs {
		sum += x
		if x < min {
			min = x
		}
		if x > max {
			max = x
		}
	}
	return Summary{
		Count: len(xs), P50: p50, P95: p95, P99: p99,
		Mean: sum / float64(len(xs)), Min: min, Max: max,
	}, true
}
