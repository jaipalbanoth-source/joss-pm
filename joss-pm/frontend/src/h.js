// Tiny hyperscript layer over React.createElement (no JSX build step is available offline).
import { createElement as ce, Fragment, isValidElement } from "../vendor/react.js";

const isProps = (x) => x && typeof x === "object" && !Array.isArray(x) && !isValidElement(x);
export function h(tag, ...args) {
  let props = null;
  if (args.length && (args[0] === null || isProps(args[0]))) props = args.shift();
  return ce(tag, props, ...args.flat(Infinity).filter((c) => c !== false && c !== null && c !== undefined));
}
const T = (t) => (...a) => h(t, ...a);
export const div = T("div"), span = T("span"), p = T("p"), button = T("button"), input = T("input"), select = T("select"),
  option = T("option"), textarea = T("textarea"), label = T("label"), table = T("table"), thead = T("thead"), tbody = T("tbody"),
  tr = T("tr"), th = T("th"), td = T("td"), h1 = T("h1"), h2 = T("h2"), h3 = T("h3"), ul = T("ul"), li = T("li"), a = T("a"),
  pre = T("pre"), small = T("small"), b = T("b"), form = T("form"), details = T("details"), summary = T("summary"), nav = T("nav"),
  header = T("header"), section = T("section"), aside = T("aside"), main = T("main"), code = T("code");
export const frag = (...c) => ce(Fragment, null, ...c.flat(Infinity));
export { ce, Fragment };
