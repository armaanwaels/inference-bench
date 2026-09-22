package loadgen

import (
	"os/exec"
	"strconv"
	"strings"
)

// gpuMemoryMiB reads used GPU memory from nvidia-smi, or 0 when there is no GPU.
func gpuMemoryMiB() int {
	out, err := exec.Command("nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits").Output()
	if err != nil {
		return 0
	}
	first, _, _ := strings.Cut(strings.TrimSpace(string(out)), "\n")
	mib, err := strconv.Atoi(strings.TrimSpace(first))
	if err != nil {
		return 0
	}
	return mib
}
