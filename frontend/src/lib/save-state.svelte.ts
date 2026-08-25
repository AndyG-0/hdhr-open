export class SaveState {
	saving = $state(false);
	saved = $state(false);
	error = $state<string | null>(null);

	async run(fn: () => Promise<void>, errorMessage: string, opts?: { setSaved?: boolean }): Promise<boolean> {
		this.saving = true;
		this.saved = false;
		this.error = null;
		try {
			await fn();
			if (opts?.setSaved !== false) this.saved = true;
			return true;
		} catch {
			this.error = errorMessage;
			return false;
		} finally {
			this.saving = false;
		}
	}
}
