// Decode-probe an mp4 with AVFoundation -- i.e. the decoder QuickTime, Finder, Photos and
// most upload validators actually use. ffmpeg is far more permissive: it honours in-band
// SPS/PPS that AVFoundation ignores, so an mp4 join can decode perfectly in ffmpeg and
// freeze in every real player. This is the tie-breaker.
// usage: avtest <file.mp4> <t1> <t2> ...
import AVFoundation
import Foundation

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: avtest <file> <t...>"); exit(2) }
let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
let gen = AVAssetImageGenerator(asset: asset)
gen.requestedTimeToleranceBefore = .zero
gen.requestedTimeToleranceAfter  = .zero
var bad = 0
for a in args.dropFirst(2) {
    guard let t = Double(a) else { continue }
    do {
        var actual = CMTime.zero
        _ = try gen.copyCGImage(at: CMTime(seconds: t, preferredTimescale: 600),
                                actualTime: &actual)
        print(String(format: "%.2fs OK", t))
    } catch {
        bad += 1
        print(String(format: "%.2fs FAILED(%@)", t, (error as NSError).localizedDescription))
    }
}
exit(bad == 0 ? 0 : 1)
