// The two Node functions fonts.test.ts uses (vitest runs in Node; the app has no Node
// types, and needs none).
declare module 'node:fs' {
  export function readFileSync(path: URL): Uint8Array
}
declare module 'node:zlib' {
  export function brotliDecompressSync(data: Uint8Array): Uint8Array
}
