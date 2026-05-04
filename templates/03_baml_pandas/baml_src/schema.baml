class BamlExtractedOutput {
  anomalies string[]
}

function ExtractAnomalies(input: string) -> BamlExtractedOutput {
  client GPT4
  prompt #"
    Extract anomalies from the following text:
    {{ input }}
  "#
}
