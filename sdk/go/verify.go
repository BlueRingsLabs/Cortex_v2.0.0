// Package cortexwebhooks verifies Cortex webhooks and decodes their typed events.
//
// A delivery carries webhook-id, webhook-timestamp and webhook-signature; the signature is
// HMAC-SHA256, under the endpoint's secret, over "{id}.{timestamp}.{body}", base64, prefixed
// "v1," (Standard Webhooks). During a secret rotation the header carries two signatures,
// space-separated, and either verifying is enough.
//
// The body is verified as the bytes received, the comparison is constant-time, and the
// timestamp must be within the tolerance (five minutes by default). Standard library only.
//
//	event, err := cortexwebhooks.Verify(secret, r.Header, body, time.Now())
//	if err != nil { http.Error(w, err.Error(), http.StatusBadRequest); return }
//	switch event.Type {
//	case cortexwebhooks.EventInvoicingInvoiceIssued:
//		var data cortexwebhooks.InvoicingInvoiceIssuedData
//		_ = json.Unmarshal(event.Data, &data)
//	}
package cortexwebhooks

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// Tolerance is how far a delivery's timestamp may differ from this machine's clock.
const Tolerance = 5 * time.Minute

// VerificationError is a delivery that must not be believed. Answer it with a 4xx other
// than 410 -- a 410 tells Cortex to stop sending to the endpoint altogether.
type VerificationError struct {
	// Reason is one of missing_header, malformed_timestamp, timestamp_too_old,
	// timestamp_too_new, malformed_secret, no_matching_signature, malformed_body.
	Reason string
}

func (e *VerificationError) Error() string { return "cortex webhook not verified: " + e.Reason }

// Event is a verified delivery's envelope. Decode Data into the struct its Type names.
type Event struct {
	Type          string          `json:"type"`
	Timestamp     string          `json:"timestamp"`
	SchemaVersion int             `json:"schema_version"`
	Data          json.RawMessage `json:"data"`
}

var digits = regexp.MustCompile(`^[0-9]+$`)

// Verify returns the delivery's event if it is genuine and fresh at now, using Tolerance.
func Verify(secret string, header http.Header, body []byte, now time.Time) (Event, error) {
	return VerifyWithin(secret, header, body, now, Tolerance)
}

// VerifyWithin is Verify with a tolerance of the caller's choosing.
func VerifyWithin(secret string, header http.Header, body []byte, now time.Time, tolerance time.Duration) (Event, error) {
	id := header.Get("webhook-id")
	timestamp := header.Get("webhook-timestamp")
	signatures := header.Get("webhook-signature")
	if id == "" || timestamp == "" || signatures == "" {
		return Event{}, &VerificationError{"missing_header"}
	}
	if !digits.MatchString(timestamp) {
		return Event{}, &VerificationError{"malformed_timestamp"}
	}
	sent, err := strconv.ParseInt(timestamp, 10, 64)
	if err != nil {
		return Event{}, &VerificationError{"malformed_timestamp"}
	}
	window := int64(tolerance / time.Second)
	if sent < now.Unix()-window {
		return Event{}, &VerificationError{"timestamp_too_old"}
	}
	if sent > now.Unix()+window {
		return Event{}, &VerificationError{"timestamp_too_new"}
	}

	encoded, found := strings.CutPrefix(secret, "whsec_")
	if !found {
		return Event{}, &VerificationError{"malformed_secret"}
	}
	key, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return Event{}, &VerificationError{"malformed_secret"}
	}
	mac := hmac.New(sha256.New, key)
	mac.Write([]byte(id + "." + timestamp + "."))
	mac.Write(body)
	expected := mac.Sum(nil)

	matched := false
	for _, candidate := range strings.Split(signatures, " ") {
		version, value, ok := strings.Cut(candidate, ",")
		if !ok || version != "v1" {
			continue
		}
		given, err := base64.StdEncoding.DecodeString(value)
		// Every candidate is compared, so the time taken does not say which one matched.
		if err == nil && hmac.Equal(given, expected) {
			matched = true
		}
	}
	if !matched {
		return Event{}, &VerificationError{"no_matching_signature"}
	}

	var event Event
	if err := json.Unmarshal(body, &event); err != nil || event.Type == "" {
		return Event{}, &VerificationError{"malformed_body"}
	}
	return event, nil
}
