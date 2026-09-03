package org.hdhropen.kit

import org.hdhropen.kit.playback.LoadingQuips
import org.junit.Assert.*
import org.junit.Test

class LoadingQuipsTest {

    @Test
    fun testDefaultQuipsNotEmpty() {
        assertTrue(LoadingQuips.defaultQuips.size >= 20)
        LoadingQuips.defaultQuips.forEach { quip ->
            assertTrue(quip.isNotBlank())
        }
    }

    @Test
    fun testGetRandomQuipWithoutExclude() {
        val quip = LoadingQuips.getRandomQuip()
        assertTrue(LoadingQuips.defaultQuips.contains(quip))
    }

    @Test
    fun testGetRandomQuipExcludesPrevious() {
        val previous = LoadingQuips.defaultQuips[0]
        repeat(20) {
            val next = LoadingQuips.getRandomQuip(exclude = previous)
            assertNotEquals(previous, next)
            assertTrue(LoadingQuips.defaultQuips.contains(next))
        }
    }

    @Test
    fun testGetRandomQuipEdgeCases() {
        assertEquals("Single", LoadingQuips.getRandomQuip(exclude = null, quips = listOf("Single")))
        assertEquals("Single", LoadingQuips.getRandomQuip(exclude = "Single", quips = listOf("Single")))
        assertEquals("Loading…", LoadingQuips.getRandomQuip(exclude = null, quips = emptyList()))
    }
}
