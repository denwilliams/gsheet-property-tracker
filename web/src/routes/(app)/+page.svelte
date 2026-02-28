<script lang="ts">
    import type { PageData } from './$types';
    import type { Property } from '$lib/types';

    let { data }: { data: PageData } = $props();

    let search = $state('');
    let areaFilter = $state('all');
    let bedsFilter = $state('any');
    let statusFilter = $state('all');
    let view = $state<'cards' | 'table'>('cards');

    let filtered = $derived(
        (data.properties as Property[]).filter((p) => {
            if (search && !p.address.toLowerCase().includes(search.toLowerCase()) &&
                !p.area?.toLowerCase().includes(search.toLowerCase())) {
                return false;
            }
            if (areaFilter !== 'all' && p.area !== areaFilter) return false;
            if (bedsFilter !== 'any') {
                const beds = parseInt(p.details?.match(/(\d+)\s*Bed/i)?.[1] ?? '0');
                if (beds !== parseInt(bedsFilter)) return false;
            }
            if (statusFilter === 'sold' && !p.sold_price) return false;
            if (statusFilter === 'active' && p.sold_price) return false;
            return true;
        })
    );

    /** Parse "$1.155" (millions shorthand) or "$1,155,000" or "$780" to a number. */
    function parsePrice(s: string): number | null {
        const m = s.match(/\$\s*([\d,]+(?:\.\d+)?)/);
        if (!m) return null;
        const raw = m[1].replace(/,/g, '');
        const n = parseFloat(raw);
        if (isNaN(n)) return null;
        // Shorthand: "$1.155" means $1,155,000 — numbers under 100 are in millions
        return n < 100 ? n * 1_000_000 : n;
    }

    /** Parse a range like "$1.1 - $1.2" into [low, high], or a single price into [p, p]. */
    function parseRange(s: string): [number, number] | null {
        const parts = s.split(/\s*-\s*/);
        if (parts.length === 2) {
            const lo = parsePrice(parts[0]);
            const hi = parsePrice(parts[1]);
            if (lo != null && hi != null) return [lo, hi];
        }
        const single = parsePrice(s);
        if (single != null) return [single, single];
        return null;
    }

    type SoldColour = 'green' | 'amber' | 'red' | null;

    /**
     * Compare sold price against advertised range.
     * - Below or bottom quarter: green
     * - Middle half: amber
     * - Top quarter or above range: red
     */
    function soldColour(prop: Property): SoldColour {
        if (!prop.sold_price || !prop.advertised_price) return null;
        const sold = parsePrice(prop.sold_price);
        const range = parseRange(prop.advertised_price);
        if (sold == null || range == null) return null;
        const [lo, hi] = range;
        if (lo === hi) return null; // single asking price, no range to compare
        if (sold > hi) return 'red';
        const position = (sold - lo) / (hi - lo); // 0 = bottom, 1 = top
        if (position <= 0.33) return 'green';
        if (position <= 0.66) return 'amber';
        return 'red';
    }

    function isAboveRange(prop: Property): boolean {
        if (!prop.sold_price || !prop.advertised_price) return false;
        const sold = parsePrice(prop.sold_price);
        const range = parseRange(prop.advertised_price);
        if (sold == null || range == null) return false;
        return range[0] !== range[1] && sold > range[1];
    }

    const soldColourClasses: Record<string, string> = {
        green: 'text-green-700',
        amber: 'text-amber-600',
        red: 'text-red-600',
    };

    const soldBorderClasses: Record<string, string> = {
        green: 'border-l-4 border-l-green-400',
        amber: 'border-l-4 border-l-amber-400',
        red: 'border-l-4 border-l-red-400',
    };

    function soldTextClass(prop: Property): string {
        const c = soldColour(prop);
        if (c === 'red') return 'text-red-600';
        if (c === 'amber') return 'text-amber-600';
        if (c === 'green') return 'text-green-700';
        if (prop.sold_price) return 'text-green-700';
        return '';
    }

    function cardBorder(prop: Property): string {
        const sc = soldColour(prop);
        if (sc) return soldBorderClasses[sc];
        return '';
    }

    /** Parse "6 Feb 2026", "19 Dec", "3 Feb" to a Date. Infers year if missing. */
    function parseSoldDate(s: string): Date | null {
        if (!s) return null;
        // If no 4-digit year, try current year first, then previous
        if (!/\d{4}/.test(s)) {
            const now = new Date();
            let d = new Date(`${s} ${now.getFullYear()}`);
            if (isNaN(d.getTime())) return null;
            if (d.getTime() > now.getTime()) {
                d = new Date(`${s} ${now.getFullYear() - 1}`);
            }
            return d;
        }
        const d = new Date(s);
        return isNaN(d.getTime()) ? null : d;
    }

    /** Format a sold_date string, adding inferred year if missing. */
    function displaySoldDate(s: string): string {
        if (!s) return '';
        // Already has a 4-digit year
        if (/\d{4}/.test(s)) return s;
        const d = parseSoldDate(s);
        if (!d) return s;
        return `${s} ${d.getFullYear()}`;
    }

    let sorted = $derived(
        [...filtered].sort((a, b) => {
            const da = parseSoldDate(a.sold_date);
            const db = parseSoldDate(b.sold_date);
            if (da && db) return db.getTime() - da.getTime();
            if (da) return -1;
            if (db) return 1;
            return 0;
        })
    );

    function timeAgo(dateStr: string | null): string {
        if (!dateStr) return 'never';
        const diff = Date.now() - new Date(dateStr).getTime();
        const hours = Math.floor(diff / 3600000);
        if (hours < 1) return 'just now';
        if (hours < 24) return `${hours}h ago`;
        const days = Math.floor(hours / 24);
        return `${days}d ago`;
    }
</script>

<div class="min-h-screen bg-gray-50">
    <header class="bg-white shadow-sm border-b">
        <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <h1 class="text-xl font-bold">Property Tracker</h1>
            <form method="POST" action="/api/logout">
                <button class="text-sm text-gray-500 hover:text-gray-700">Logout</button>
            </form>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-6">
        <div class="bg-white rounded-lg shadow-sm border p-4 mb-6 space-y-3">
            <input
                type="text" placeholder="Search by address or area..."
                bind:value={search}
                class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <div class="flex flex-wrap gap-3 items-center">
                <select bind:value={areaFilter} class="border border-gray-300 rounded px-2 py-1 text-sm">
                    <option value="all">All Areas</option>
                    {#each data.areas as area}
                        <option value={area}>{area}</option>
                    {/each}
                </select>
                <select bind:value={bedsFilter} class="border border-gray-300 rounded px-2 py-1 text-sm">
                    <option value="any">Any Beds</option>
                    {#each [1,2,3,4,5] as n}
                        <option value={String(n)}>{n} Bed</option>
                    {/each}
                </select>
                <select bind:value={statusFilter} class="border border-gray-300 rounded px-2 py-1 text-sm">
                    <option value="all">All Status</option>
                    <option value="active">Active</option>
                    <option value="sold">Sold</option>
                </select>
                <div class="ml-auto flex gap-1">
                    <button
                        onclick={() => view = 'cards'}
                        class="px-3 py-1 text-sm rounded {view === 'cards' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'}"
                    >Cards</button>
                    <button
                        onclick={() => view = 'table'}
                        class="px-3 py-1 text-sm rounded {view === 'table' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'}"
                    >Table</button>
                </div>
                <span class="text-sm text-gray-500">{filtered.length} properties</span>
            </div>
        </div>

        {#if view === 'cards'}
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {#each sorted as prop (prop.id)}
                    <a
                        href="/property/{prop.id}"
                        class="bg-white rounded-lg shadow-sm border overflow-hidden hover:shadow-md transition-shadow
                            {cardBorder(prop)}"
                    >
                        {#if prop.hero_image}
                            <img
                                src="/images/{prop.id}/{prop.hero_image}"
                                alt={prop.address}
                                class="w-full h-40 object-cover"
                                loading="lazy"
                            />
                        {:else}
                            <div class="w-full h-24 bg-gray-100 flex items-center justify-center">
                                <span class="text-gray-300 text-3xl">&#9633;</span>
                            </div>
                        {/if}
                        <div class="p-4">
                            <h3 class="font-semibold text-sm leading-tight mb-2">{prop.address}</h3>
                            <div class="text-xs text-gray-500 space-y-1">
                                {#if prop.details}<p>{prop.details}</p>{/if}
                                {#if prop.area}<p>{prop.area}</p>{/if}
                                {#if prop.advertised_price}
                                    <p class="text-sm font-medium text-gray-900">{prop.advertised_price}</p>
                                {/if}
                                {#if prop.sold_price}
                                    <p class="font-medium {soldTextClass(prop)}">
                                        Sold: {prop.sold_price}
                                        {#if isAboveRange(prop)}
                                            <span class="text-xs font-normal">(above range)</span>
                                        {/if}
                                    </p>
                                    {#if prop.sold_date}
                                        <p class="text-gray-400">{displaySoldDate(prop.sold_date)}</p>
                                    {/if}
                                {/if}
                                {#if prop.has_recent_changes}
                                    <p class="text-amber-600 text-xs">Updated {timeAgo(prop.last_change_at)}</p>
                                {/if}
                            </div>
                        </div>
                    </a>
                {/each}
            </div>
        {/if}

        {#if view === 'table'}
            <div class="bg-white rounded-lg shadow-sm border overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="bg-gray-50 border-b">
                        <tr>
                            <th class="text-left px-4 py-2 font-medium">Address</th>
                            <th class="text-left px-4 py-2 font-medium">Details</th>
                            <th class="text-left px-4 py-2 font-medium">Area</th>
                            <th class="text-left px-4 py-2 font-medium">Price</th>
                            <th class="text-left px-4 py-2 font-medium">Sold</th>
                            <th class="text-left px-4 py-2 font-medium">Sold Date</th>
                            <th class="text-left px-4 py-2 font-medium">Checked</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each sorted as prop (prop.id)}
                            <tr class="border-b hover:bg-gray-50 {soldColour(prop) === 'red' ? 'bg-red-50' : soldColour(prop) === 'green' ? 'bg-green-50' : soldColour(prop) === 'amber' ? 'bg-amber-50' : ''}">
                                <td class="px-4 py-2">
                                    <a href="/property/{prop.id}" class="text-blue-600 hover:underline">{prop.address}</a>
                                </td>
                                <td class="px-4 py-2 text-gray-600">{prop.details || '-'}</td>
                                <td class="px-4 py-2 text-gray-600">{prop.area || '-'}</td>
                                <td class="px-4 py-2">{prop.advertised_price || '-'}</td>
                                <td class="px-4 py-2 {soldTextClass(prop)}">
                                    {prop.sold_price || '-'}
                                    {#if isAboveRange(prop)}
                                        <span class="text-xs">(above)</span>
                                    {/if}
                                </td>
                                <td class="px-4 py-2 text-gray-500 text-xs">{displaySoldDate(prop.sold_date) || '-'}</td>
                                <td class="px-4 py-2 text-gray-400 text-xs">{timeAgo(prop.last_checked)}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    </main>
</div>
