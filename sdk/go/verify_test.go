package cortexwebhooks

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"sort"
	"testing"
	"time"
)

// The vectors are signed by the platform's own signing code (../vectors.json), so passing
// them means this verifier accepts what Cortex actually sends and refuses what it must.
type vector struct {
	Name    string            `json:"name"`
	Secret  string            `json:"secret"`
	Headers map[string]string `json:"headers"`
	Body    string            `json:"body"`
	Now     int64             `json:"now"`
	Expect  struct {
		OK     bool   `json:"ok"`
		Type   string `json:"type"`
		Reason string `json:"reason"`
	} `json:"expect"`
}

type vectors struct {
	Vectors    []vector `json:"vectors"`
	EventTypes []string `json:"event_types"`
}

func load(t *testing.T) vectors {
	t.Helper()
	raw, err := os.ReadFile("../vectors.json")
	if err != nil {
		t.Fatal(err)
	}
	var loaded vectors
	if err := json.Unmarshal(raw, &loaded); err != nil {
		t.Fatal(err)
	}
	return loaded
}

func TestTheVectorsThePlatformSigned(t *testing.T) {
	for _, v := range load(t).Vectors {
		t.Run(v.Name, func(t *testing.T) {
			header := http.Header{}
			for name, value := range v.Headers {
				header.Set(name, value)
			}
			event, err := Verify(v.Secret, header, []byte(v.Body), time.Unix(v.Now, 0))
			if v.Expect.OK {
				if err != nil {
					t.Fatalf("refused a genuine delivery: %v", err)
				}
				if event.Type != v.Expect.Type {
					t.Fatalf("type %q, want %q", event.Type, v.Expect.Type)
				}
				return
			}
			var refused *VerificationError
			if !errors.As(err, &refused) || refused.Reason != v.Expect.Reason {
				t.Fatalf("got %v, want refusal %q", err, v.Expect.Reason)
			}
		})
	}
}

func TestEveryEventTypeIsKnown(t *testing.T) {
	want := load(t).EventTypes
	got := append([]string(nil), EventTypes...)
	sort.Strings(want)
	sort.Strings(got)
	if len(got) != len(want) {
		t.Fatalf("event types %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("event types %v, want %v", got, want)
		}
	}
}
