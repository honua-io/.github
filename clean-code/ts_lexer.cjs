// Reads [{path, text}] JSON on stdin; writes {path: {tokens, comments, functions, error}} JSON on stdout.
// Tokens come from the TypeScript parser's tree, so regex, template and JSX text lex exactly as the compiler sees them.
const ts = require("typescript");
const { outputNames } = require("./ts_outputs.cjs");

const SCRIPT_KINDS = {
  ".ts": ts.ScriptKind.TS, ".mts": ts.ScriptKind.TS, ".cts": ts.ScriptKind.TS, ".tsx": ts.ScriptKind.TSX,
  ".js": ts.ScriptKind.JS, ".mjs": ts.ScriptKind.JS, ".cjs": ts.ScriptKind.JS, ".jsx": ts.ScriptKind.JSX,
};
const LINE_BREAK = /[\r\n\u2028\u2029]/;

function scriptKind(path) {
  const dot = path.lastIndexOf(".");
  return SCRIPT_KINDS[path.slice(dot)] ?? ts.ScriptKind.TS;
}

function lineOf(source, position) {
  return source.getLineAndCharacterOfPosition(position).line + 1;
}

function isJsDoc(node) {
  return node.kind >= ts.SyntaxKind.FirstJSDocNode && node.kind <= ts.SyntaxKind.LastJSDocNode;
}

function isEmptyJsxExpression(node) {
  return node.kind === ts.SyntaxKind.JsxExpression && !node.expression;
}

// JSX text is compared exactly, child by child. Only whitespace-only text spanning a line break is dropped,
// as the JSX transform drops it; deleting a {/* comment */} between two texts changes the children and fails.
function collectTokens(source) {
  const tokens = [];
  const visit = (node) => {
    if (isJsDoc(node) || isEmptyJsxExpression(node) || node.containsOnlyTriviaWhiteSpaces) return;
    const children = node.getChildren(source);
    if (children.length > 0) return children.forEach(visit);
    const isJsxText = node.kind === ts.SyntaxKind.JsxText;
    const text = isJsxText ? node.getFullText(source) : node.getText(source);
    if (!text) return;
    const trivia = source.text.slice(node.getFullStart(), node.getStart(source));
    tokens.push([text, lineOf(source, node.getStart(source)), !isJsxText && LINE_BREAK.test(trivia) ? "\n" : ""]);
  };
  visit(source);
  return tokens;
}

function collectComments(source) {
  const comments = [];
  const seen = new Set();
  const addRange = (start, end) => {
    if (seen.has(start)) return;
    seen.add(start);
    const first = lineOf(source, start);
    source.text.slice(start, end).split("\n").forEach((text, index) => comments.push([first + index, text]));
  };
  const visit = (node) => {
    ts.forEachLeadingCommentRange(source.text, node.getFullStart(), addRange);
    ts.forEachTrailingCommentRange(source.text, node.getEnd(), addRange);
    node.getChildren(source).forEach(visit);
  };
  visit(source);
  return comments.sort((a, b) => a[0] - b[0]);
}

function functionName(node, source) {
  if (node.name) return node.name.getText(source);
  if (node.parent && ts.isVariableDeclaration(node.parent)) return node.parent.name.getText(source);
  if (node.parent && ts.isPropertyAssignment(node.parent)) return node.parent.name.getText(source);
  return node.kind === ts.SyntaxKind.Constructor ? "constructor" : "<anonymous>";
}

function isBooleanParameter(parameter) {
  const initializer = parameter.initializer?.kind;
  const booleanLiteral = initializer === ts.SyntaxKind.TrueKeyword || initializer === ts.SyntaxKind.FalseKeyword;
  return parameter.type?.kind === ts.SyntaxKind.BooleanKeyword || booleanLiteral;
}

function describeFunction(node, source, checker) {
  const outputs = outputNames(node, checker);
  const parameters = node.parameters.map((parameter) => [
    parameter.name.getText(source), isBooleanParameter(parameter), outputs.has(parameter.name.getText(source)),
  ]);
  const start = lineOf(source, node.getStart(source));
  return [functionName(node, source), start, lineOf(source, node.getEnd()), parameters, ts.isConstructorDeclaration(node)];
}

function collectFunctions(source, checker) {
  const functions = [];
  const visit = (node) => {
    if (ts.isFunctionLike(node) && node.body) functions.push(describeFunction(node, source, checker));
    ts.forEachChild(node, visit);
  };
  visit(source);
  return functions;
}

function lex({ path, text }) {
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, scriptKind(path));
  const host = {
    getSourceFile: (name) => name === path ? source : undefined,
    writeFile: () => {}, getCurrentDirectory: () => "", getDirectories: () => [],
    fileExists: (name) => name === path, readFile: (name) => name === path ? text : undefined,
    getCanonicalFileName: (name) => name, useCaseSensitiveFileNames: () => true,
    getNewLine: () => "\n", getDefaultLibFileName: () => "",
  };
  const checker = ts.createProgram([path], { noLib: true, noResolve: true }, host).getTypeChecker();
  const diagnostics = source.parseDiagnostics ?? [];
  const error = diagnostics.length ? ts.flattenDiagnosticMessageText(diagnostics[0].messageText, " ") : null;
  return { tokens: collectTokens(source), comments: collectComments(source), functions: collectFunctions(source, checker), error };
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const results = Object.fromEntries(JSON.parse(input).map((file) => [file.path, lex(file)]));
  process.stdout.write(JSON.stringify(results));
});
