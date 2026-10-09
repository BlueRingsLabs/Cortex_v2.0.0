module github.com/BlueRingsLabs/Cortex_v2.0.0/examples/go

go 1.22

require github.com/BlueRingsLabs/Cortex_v2.0.0/sdk/go v0.0.0

// The SDK beside it in this repository. In your own module, drop this line and `go get` the SDK.
replace github.com/BlueRingsLabs/Cortex_v2.0.0/sdk/go => ../../sdk/go
