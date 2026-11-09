import Foundation
import Vision

guard CommandLine.arguments.count > 1 else {
    print("{}")
    exit(0)
}

let imagePath = CommandLine.arguments[1]
let imageURL = URL(fileURLWithPath: imagePath)
let handler = VNImageRequestHandler(url: imageURL, options: [:])

let textRequest = VNRecognizeTextRequest()
textRequest.recognitionLevel = .accurate
textRequest.usesLanguageCorrection = true

let classifyRequest = VNClassifyImageRequest()

do {
    try handler.perform([textRequest, classifyRequest])
} catch {
    print("{}")
    exit(0)
}

var lines: [String] = []
if let results = textRequest.results {
    for obs in results.prefix(8) {
        if let top = obs.topCandidates(1).first {
            let str = top.string.trimmingCharacters(in: .whitespacesAndNewlines)
            if str.count > 1 && !lines.contains(str) {
                lines.append(str)
            }
        }
    }
}

var tags: [String] = []
if let classResults = classifyRequest.results {
    for c in classResults.filter({ $0.confidence > 0.35 }).prefix(5) {
        let parts = c.identifier.components(separatedBy: "_")
        let cleaned = parts.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        if !tags.contains(cleaned) {
            tags.append(cleaned)
        }
    }
}

let result: [String: Any] = [
    "ocr_text": lines.joined(separator: " — "),
    "tags": tags
]

if let jsonData = try? JSONSerialization.data(withJSONObject: result, options: []),
   let jsonStr = String(data: jsonData, encoding: .utf8) {
    print(jsonStr)
}
