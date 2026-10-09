// A Cortex webhook receiver in Go, standard library only.
//
//	CORTEX_WEBHOOK_SECRET=whsec_... go run ./examples/go 8083
//
// Verify the raw body before parsing it, answer quickly, ignore a delivery already handled
// (delivery is at least once: a retry or a replay carries the same webhook-id), and refuse
// what does not verify with a 400.
package main

import (
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	cortexwebhooks "github.com/BlueRingsLabs/Cortex_v2.0.0/sdk/go"
)

const maxBody = 1 << 20

func main() {
	secret := os.Getenv("CORTEX_WEBHOOK_SECRET")
	if secret == "" {
		log.Fatal("CORTEX_WEBHOOK_SECRET is not set")
	}
	port := "8083"
	if len(os.Args) > 1 {
		port = os.Args[1]
	}

	// Message ids already handled. In production: a table with a unique constraint.
	var mu sync.Mutex
	handled := map[string]bool{}

	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(io.LimitReader(r.Body, maxBody+1))
		if err != nil || len(body) > maxBody {
			http.Error(w, "too large", http.StatusRequestEntityTooLarge)
			return
		}
		event, err := cortexwebhooks.Verify(secret, r.Header, body, time.Now())
		if err != nil {
			var refused *cortexwebhooks.VerificationError
			if errors.As(err, &refused) {
				http.Error(w, refused.Reason, http.StatusBadRequest)
				return
			}
			http.Error(w, "invalid", http.StatusBadRequest)
			return
		}
		id := r.Header.Get("webhook-id")
		mu.Lock()
		seen := handled[id]
		handled[id] = true
		mu.Unlock()
		if seen {
			fmt.Printf("duplicate %s\n", id)
		} else {
			fmt.Printf("received %s %s\n", event.Type, id)
		}
		w.WriteHeader(http.StatusNoContent)
	})
	log.Fatal(http.ListenAndServe("127.0.0.1:"+port, nil))
}
