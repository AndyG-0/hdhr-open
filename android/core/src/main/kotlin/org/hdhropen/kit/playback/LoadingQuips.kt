package org.hdhropen.kit.playback

object LoadingQuips {
    val defaultQuips = listOf(
        "Adjusting the rabbit ears…",
        "Blowing the dust out of the coaxial cable…",
        "Reticulating broadcast splines…",
        "Negotiating with the local TV tower…",
        "Polishing the UHF antenna…",
        "Aligning flux capacitors with the tuner frequency…",
        "Summoning pixels from the ether…",
        "Demodulating high-definition electrons…",
        "Consulting the TV Guide from 1998…",
        "Wrapping the antenna in aluminum foil for better reception…",
        "Bribing the broadcast engineers with coffee…",
        "Warming up the cathode ray tube…",
        "Untangling the MPEG-TS transport stream…",
        "Tuning into the quantum frequency…",
        "Teaching ffmpeg some manners…",
        "Shaking the tuner to loosen up the bits…",
        "Hunting for stray electrons in the coaxial line…",
        "Asking SiliconDust nicely for the next keyframe…",
        "Checking the weather for atmospheric interference…",
        "Calibrating the antenna rotor motor…",
        "Buffering the dramatic pauses…",
        "Counting dropped frames so you don't have to…",
        "De-interlacing the space-time continuum…",
        "Searching for the remote between the couch cushions…",
        "Spinning up the digital hamster wheel…",
        "Feeding the silicon dust bunnies…",
        "Re-pointing the antenna toward the north star…",
        "Herding stray packets across the LAN…"
    )

    fun getRandomQuip(exclude: String? = null, quips: List<String> = defaultQuips): String {
        if (quips.isEmpty()) return "Loading…"
        if (quips.size == 1) return quips.first()
        val pool = if (exclude != null) quips.filter { it != exclude } else quips
        val candidates = if (pool.isNotEmpty()) pool else quips
        return candidates.random()
    }
}
