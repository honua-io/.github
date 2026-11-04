import typescriptParser from "@typescript-eslint/parser";
import sonarjs from "eslint-plugin-sonarjs";
import budgets from "./budgets.json" with { type: "json" };

const TEST_FILES = ["**/*.{test,spec}.*", "**/{test,tests,__tests__,e2e}/**"];

export default [
  {
    files: ["**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}"],
    languageOptions: {
      parser: typescriptParser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: "off" },
    plugins: { sonarjs },
    rules: {
      "max-params": ["error", budgets.parameters],
      "max-depth": ["warn", budgets.nestingDepth],
      complexity: ["warn", budgets.complexity],
      "no-magic-numbers": [
        "warn",
        { ignore: [-1, 0, 1, 2], ignoreArrayIndexes: true, ignoreDefaultValues: true, ignoreClassFieldInitialValues: true },
      ],
      "sonarjs/cognitive-complexity": ["warn", budgets.cognitiveComplexity],
      "sonarjs/no-identical-functions": "error",
      "sonarjs/no-duplicate-string": "warn",
      "sonarjs/no-commented-code": "error",
    },
  },
  {
    files: TEST_FILES,
    rules: { "no-magic-numbers": "off", "sonarjs/no-duplicate-string": "off" },
  },
];
