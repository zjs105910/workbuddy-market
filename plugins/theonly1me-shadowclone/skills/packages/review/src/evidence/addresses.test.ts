import { expect, test } from "bun:test";
import { isPublicAddress } from "./addresses";
import { htmlToText } from "./fetchPage";

test("private, loopback, link-local, and metadata addresses are not fetched", () => {
  const internal = ["10.1.2.3", "127.0.0.1", "169.254.169.254", "172.20.0.5", "192.168.1.1", "100.64.0.1", "::1", "fd12::1", "fe80::1", "::ffff:10.0.0.1"];

  expect(internal.filter((address) => isPublicAddress(address))).toEqual([]);
});

test("public addresses are fetched", () => {
  expect(["93.184.216.34", "8.8.8.8", "2606:4700::1111"].every((address) => isPublicAddress(address))).toBe(true);
});

test("page text keeps prose and drops scripts and tags", () => {
  expect(htmlToText("<p>Use <code>verify=True</code> &amp; pin certs.</p><script>alert(1)</script>")).toBe("Use verify=True & pin certs.");
});
