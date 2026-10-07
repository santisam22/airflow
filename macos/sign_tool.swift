// Signs Airflow updates with an Ed25519 key kept in your login Keychain.
//
//   swift macos/sign_tool.swift genkey        create the key (once), print the public key
//   swift macos/sign_tool.swift pubkey        print the public key
//   swift macos/sign_tool.swift sign <file>   print a base64 signature of <file>
//
// The public key goes in airflow/config.py (UPDATE_PUBLIC_KEY). Airflow refuses any
// update whose signature doesn't verify against it.

import CryptoKit
import Foundation

let service = "airflow-release-signing"
let account = "ed25519"

func security(_ args: [String], input: String? = nil) -> (status: Int32, output: String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/security")
    p.arguments = args
    let out = Pipe(), inp = Pipe()
    p.standardOutput = out
    p.standardError = FileHandle.nullDevice
    if input != nil { p.standardInput = inp }
    do { try p.run() } catch { return (-1, "") }
    if let input {  // via stdin so the key never appears in a process argument list
        inp.fileHandleForWriting.write(Data(input.utf8))
        inp.fileHandleForWriting.closeFile()
    }
    let data = out.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines))
}

func loadKey() -> Curve25519.Signing.PrivateKey? {
    let r = security(["find-generic-password", "-s", service, "-a", account, "-w"])
    guard r.status == 0, let raw = Data(base64Encoded: r.output) else { return nil }
    return try? Curve25519.Signing.PrivateKey(rawRepresentation: raw)
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

let args = CommandLine.arguments.dropFirst()
switch args.first {
case "genkey":
    if loadKey() != nil { fail("A signing key already exists in your Keychain; not replacing it.") }
    let key = Curve25519.Signing.PrivateKey()
    let b64 = key.rawRepresentation.base64EncodedString()  // base64: no quotes or spaces to escape
    let cmd = "add-generic-password -s \"\(service)\" -a \"\(account)\" -l \"Airflow release signing key\" -w \"\(b64)\"\n"
    guard security(["-i"], input: cmd).status == 0, loadKey() != nil else { fail("Couldn't save the key to your Keychain.") }
    print(key.publicKey.rawRepresentation.base64EncodedString())
case "pubkey":
    guard let key = loadKey() else { fail("No signing key. Run: swift macos/sign_tool.swift genkey") }
    print(key.publicKey.rawRepresentation.base64EncodedString())
case "sign":
    guard args.count == 2, let path = args.last else { fail("Usage: sign <file>") }
    guard let key = loadKey() else { fail("No signing key. Run: swift macos/sign_tool.swift genkey") }
    guard let data = FileManager.default.contents(atPath: path) else { fail("Can't read \(path)") }
    guard let signature = try? key.signature(for: data) else { fail("Signing failed") }
    print(signature.base64EncodedString())
default:
    fail("Usage: swift macos/sign_tool.swift genkey | pubkey | sign <file>")
}
