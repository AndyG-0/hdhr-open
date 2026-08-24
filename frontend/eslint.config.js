import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';
import globals from 'globals';

export default tseslint.config(
	{
		ignores: ['build/', '.svelte-kit/', 'node_modules/', 'coverage/'],
	},
	js.configs.recommended,
	...tseslint.configs.recommended,
	...svelte.configs.recommended,
	prettier,
	...svelte.configs.prettier,
	{
		languageOptions: {
			globals: { ...globals.browser, ...globals.node },
		},
	},
	{
		files: ['**/*.svelte'],
		languageOptions: {
			parserOptions: {
				parser: tseslint.parser,
			},
		},
	},
	{
		rules: {
			// This plugin version tokenizes everything after the ignore code as
			// more codes, so the `-- explanation` suffix the codebase uses on
			// svelte-ignore comments (a documented Svelte convention) reads as
			// unused codes rather than a comment. False positive, not dead code.
			'svelte/no-unused-svelte-ignore': 'off',
			// Requires adopting SvelteKit's typed-routing resolve() wrapper
			// around every goto()/href in the app — an intentional API adoption
			// decision, not a lint fix, and unused anywhere in this codebase.
			'svelte/no-navigation-without-resolve': 'off',
			// Flags the codebase's copy-on-write Set pattern (`$state(new
			// Set())`, mutate a copy, reassign) as needing SvelteSet instead.
			// That pattern is correct under Svelte 5 reactivity; switching
			// classes is a refactor choice, not a bug.
			'svelte/prefer-svelte-reactivity': 'off',
		},
	},
);
