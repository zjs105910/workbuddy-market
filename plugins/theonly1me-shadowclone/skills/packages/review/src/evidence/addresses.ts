import { isIP } from "node:net";

type Ipv4Range = { readonly name: string; readonly base: string; readonly bits: number };

const ipv4RangesThatAreNotPubliclyRoutable: readonly Ipv4Range[] = [
  { name: "this network, RFC 791", base: "0.0.0.0", bits: 8 },
  { name: "private, RFC 1918", base: "10.0.0.0", bits: 8 },
  { name: "carrier-grade NAT, RFC 6598", base: "100.64.0.0", bits: 10 },
  { name: "loopback, RFC 1122", base: "127.0.0.0", bits: 8 },
  { name: "link-local and cloud metadata, RFC 3927", base: "169.254.0.0", bits: 16 },
  { name: "private, RFC 1918", base: "172.16.0.0", bits: 12 },
  { name: "IETF protocol assignments, RFC 6890", base: "192.0.0.0", bits: 24 },
  { name: "private, RFC 1918", base: "192.168.0.0", bits: 16 },
  { name: "benchmarking, RFC 2544", base: "198.18.0.0", bits: 15 },
  { name: "multicast and reserved, RFC 5771 and RFC 1112", base: "224.0.0.0", bits: 3 },
];

const ipv6PrefixesThatAreNotPubliclyRoutable: readonly { readonly name: string; readonly pattern: RegExp }[] = [
  { name: "unspecified and loopback, RFC 4291", pattern: /^::1?$/ },
  { name: "unique local, RFC 4193", pattern: /^f[cd][0-9a-f]{2}:/ },
  { name: "link-local, RFC 4291", pattern: /^fe[89ab][0-9a-f]:/ },
];

function ipv4Number(address: string): number {
  return address.split(".").reduce((total, octet) => total * 256 + Number(octet), 0);
}

function isPublicIpv4(address: string): boolean {
  const value = ipv4Number(address);

  return !ipv4RangesThatAreNotPubliclyRoutable.some(({ base, bits }) => {
    const size = 2 ** (32 - bits);

    return Math.floor(value / size) === Math.floor(ipv4Number(base) / size);
  });
}

export function isPublicAddress(address: string): boolean {
  const version = isIP(address);

  if (version === 4) {
    return isPublicIpv4(address);
  }

  if (version !== 6) {
    return false;
  }

  const lower = address.toLowerCase();
  const mapped = /^::ffff:(\d+\.\d+\.\d+\.\d+)$/.exec(lower)?.[1];

  if (mapped !== undefined) {
    return isPublicIpv4(mapped);
  }

  return !ipv6PrefixesThatAreNotPubliclyRoutable.some(({ pattern }) => pattern.test(lower));
}
