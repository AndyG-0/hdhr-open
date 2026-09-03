export const DEFAULT_LOADING_QUIPS = [
	'Adjusting the rabbit ears…',
	'Blowing the dust out of the coaxial cable…',
	'Reticulating broadcast splines…',
	'Negotiating with the local TV tower…',
	'Polishing the UHF antenna…',
	'Aligning flux capacitors with the tuner frequency…',
	'Summoning pixels from the ether…',
	'Demodulating high-definition electrons…',
	'Consulting the TV Guide from 1998…',
	'Wrapping the antenna in aluminum foil for better reception…',
	'Bribing the broadcast engineers with coffee…',
	'Warming up the cathode ray tube…',
	'Untangling the MPEG-TS transport stream…',
	'Tuning into the quantum frequency…',
	'Teaching ffmpeg some manners…',
	'Shaking the tuner to loosen up the bits…',
	'Hunting for stray electrons in the coaxial line…',
	'Asking SiliconDust nicely for the next keyframe…',
	'Checking the weather for atmospheric interference…',
	'Calibrating the antenna rotor motor…',
	'Buffering the dramatic pauses…',
	'Counting dropped frames so you don\'t have to…',
	'De-interlacing the space-time continuum…',
	'Searching for the remote between the couch cushions…',
	'Spinning up the digital hamster wheel…',
	'Feeding the silicon dust bunnies…',
	'Re-pointing the antenna toward the north star…',
	'Herding stray packets across the LAN…'
];

/**
 * Returns a random quip from the list, ensuring it does not repeat the previous one
 * if multiple options are available.
 */
export function getNextLoadingQuip(previousQuip?: string, quips: string[] = DEFAULT_LOADING_QUIPS): string {
	if (!quips || quips.length === 0) {
		return 'Loading…';
	}
	if (quips.length === 1) {
		return quips[0];
	}
	const pool = previousQuip ? quips.filter((q) => q !== previousQuip) : quips;
	const candidates = pool.length > 0 ? pool : quips;
	const index = Math.floor(Math.random() * candidates.length);
	return candidates[index];
}
