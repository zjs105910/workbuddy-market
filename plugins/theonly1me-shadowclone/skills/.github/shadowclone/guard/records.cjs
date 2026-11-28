function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function record(value) {
  return isRecord(value) ? value : {};
}
function records(value) {
  return Array.isArray(value) ? value.map(record) : [];
}
async function readGithub(options) {
  return record((await options.request(options.route, options.parameters)).data);
}
async function readIssueEvents(options) {
  const events = [];
  for (let page = 1;page <= 10; page++) {
    const entries = records((await options.request(options.route, { per_page: 100, page })).data);
    events.push(...entries);
    if (entries.length < 100) {
      return events;
    }
  }
  return null;
}
function positiveNumber(value) {
  const number = typeof value === "number" ? value : typeof value === "string" && /^\d+$/.test(value) ? Number(value) : 0;
  return Number.isSafeInteger(number) && number > 0 ? number : null;
}

module.exports = { isRecord, record, records, readGithub, readIssueEvents, positiveNumber };
