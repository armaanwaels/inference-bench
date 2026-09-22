package stats

import "testing"

func TestPercentileNearestRank(t *testing.T) {
	xs := []float64{10, 20, 30, 40, 50, 60, 70, 80, 90, 100}
	cases := []struct {
		p    float64
		want float64
	}{
		{50, 50}, // rank ceil(0.5*10)=5
		{95, 100},
		{99, 100},
		{0.1, 10},
		{100, 100},
	}
	for _, c := range cases {
		got, ok := Percentile(xs, c.p)
		if !ok || got != c.want {
			t.Errorf("Percentile(p=%v) = %v, %v; want %v", c.p, got, ok, c.want)
		}
	}
}

func TestPercentileUnsortedInputDoesNotMutate(t *testing.T) {
	xs := []float64{30, 10, 20}
	if got, _ := Percentile(xs, 50); got != 20 {
		t.Errorf("p50 = %v, want 20", got)
	}
	if xs[0] != 30 {
		t.Errorf("input was reordered: %v", xs)
	}
}

func TestPercentileSingleSample(t *testing.T) {
	for _, p := range []float64{0.5, 50, 99, 100} {
		got, ok := Percentile([]float64{7}, p)
		if !ok || got != 7 {
			t.Errorf("Percentile([7], %v) = %v, %v", p, got, ok)
		}
	}
}

func TestPercentileRejectsEmptyAndBadP(t *testing.T) {
	if _, ok := Percentile(nil, 50); ok {
		t.Error("empty input reported ok")
	}
	if _, ok := Percentile([]float64{1}, 101); ok {
		t.Error("p=101 reported ok")
	}
	if _, ok := Percentile([]float64{1}, -1); ok {
		t.Error("p=-1 reported ok")
	}
}

func TestDescribe(t *testing.T) {
	s, ok := Describe([]float64{1, 2, 3, 4})
	if !ok {
		t.Fatal("Describe reported not ok")
	}
	if s.Count != 4 || s.Min != 1 || s.Max != 4 || s.Mean != 2.5 || s.P50 != 2 {
		t.Errorf("unexpected summary: %+v", s)
	}
	if _, ok := Describe(nil); ok {
		t.Error("empty Describe reported ok")
	}
}
