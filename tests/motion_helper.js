// Runs a movement script through app/play/motion.js, for tests/test_motion_cross.py.
// Usage: deno run --allow-read tests/motion_helper.js script.json
// The script is {dt, start: state, inputs: [input, ...]}; prints the state after each step as JSON.
import { step } from "../app/play/motion.js";

const map = JSON.parse(await Deno.readTextFile(new URL("../app/shared/map.json", import.meta.url)));
const script = JSON.parse(await Deno.readTextFile(Deno.args[0]));
let s = script.start;
const out = [];
for (const input of script.inputs) {
  s = step(s, input, script.dt, map);
  out.push(s);
}
console.log(JSON.stringify(out));
