// face-landmarks.swift — per-frame face geometry via Apple's Vision framework.
//
// Used by measure-face-band.py on macOS. A luminance heuristic cannot reliably
// find a head in a real room: dark wall art above the subject reads as a crown,
// and a black t-shirt reads as a face. Vision does not have those failure modes
// and is fast enough to run every frame of a 60s clip.
//
//   swiftc -O -o face-landmarks face-landmarks.swift
//   ./face-landmarks frame1.png frame2.png ...
//
// Emits one JSON object per line, in argument order, to stdout:
//   {"f":"<path>","ok":true,"conf":1.0,"boxTop":..,"boxBottom":..,
//    "boxLeft":..,"boxRight":..,"eyeTop":..,"eyeCenter":..,"chin":..}
// All y values are in PIXELS from the TOP of the image (not Vision's
// bottom-left normalized space), so the caller can use them directly.
// A frame with no detected face emits {"f":..,"ok":false}.

import Foundation
import Vision
import CoreImage
import AppKit

func emit(_ d: [String: Any]) {
    if let j = try? JSONSerialization.data(withJSONObject: d),
       let s = String(data: j, encoding: .utf8) {
        print(s)
    }
}

let paths = Array(CommandLine.arguments.dropFirst())
if paths.isEmpty {
    FileHandle.standardError.write("usage: face-landmarks <image> [image ...]\n".data(using: .utf8)!)
    exit(2)
}

for path in paths {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        emit(["f": path, "ok": false, "err": "unreadable"]); continue
    }
    let H = Double(cg.height), W = Double(cg.width)

    let req = VNDetectFaceLandmarksRequest()
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch {
        emit(["f": path, "ok": false, "err": "vision: \(error)"]); continue
    }
    guard let face = req.results?
            .max(by: { $0.boundingBox.height < $1.boundingBox.height }) else {
        emit(["f": path, "ok": false]); continue
    }

    // Vision: normalized, origin bottom-left. Flip y to top-origin pixels.
    let bb = face.boundingBox
    let boxTop = (1.0 - bb.maxY) * H
    let boxBottom = (1.0 - bb.minY) * H
    let boxLeft = bb.minX * W
    let boxRight = bb.maxX * W

    var out: [String: Any] = [
        "f": path, "ok": true, "conf": Double(face.confidence),
        "boxTop": boxTop, "boxBottom": boxBottom,
        "boxLeft": boxLeft, "boxRight": boxRight,
    ]

    // Landmarks are normalized to the face box, origin bottom-left.
    func toPixelY(_ p: CGPoint) -> Double {
        let ny = bb.minY + Double(p.y) * bb.height
        return (1.0 - ny) * H
    }
    if let lm = face.landmarks {
        var eyeYs: [Double] = []
        for region in [lm.leftEye, lm.rightEye] {
            guard let r = region else { continue }
            eyeYs.append(contentsOf: r.normalizedPoints.map(toPixelY))
        }
        if !eyeYs.isEmpty {
            out["eyeTop"] = eyeYs.min()!              // upper lid: the real floor
            out["eyeCenter"] = eyeYs.reduce(0,+) / Double(eyeYs.count)
        }
        var browYs: [Double] = []
        for region in [lm.leftEyebrow, lm.rightEyebrow] {
            guard let r = region else { continue }
            browYs.append(contentsOf: r.normalizedPoints.map(toPixelY))
        }
        if !browYs.isEmpty { out["browTop"] = browYs.min()! }

        if let contour = lm.faceContour {
            let ys = contour.normalizedPoints.map(toPixelY)
            if let c = ys.max() { out["chin"] = c }
        }
    }
    emit(out)
}
