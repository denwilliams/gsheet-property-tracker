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
                {#each filtered as prop (prop.id)}
                    <a
                        href="/property/{prop.id}"
                        class="bg-white rounded-lg shadow-sm border p-4 hover:shadow-md transition-shadow
                            {prop.has_recent_changes ? 'border-l-4 border-l-amber-400' : ''}"
                    >
                        <h3 class="font-semibold text-sm leading-tight mb-2">{prop.address}</h3>
                        <div class="text-xs text-gray-500 space-y-1">
                            {#if prop.details}<p>{prop.details}</p>{/if}
                            {#if prop.area}<p>{prop.area}</p>{/if}
                            {#if prop.advertised_price}
                                <p class="text-sm font-medium text-gray-900">{prop.advertised_price}</p>
                            {/if}
                            {#if prop.sold_price}
                                <p class="text-green-700 font-medium">Sold: {prop.sold_price}</p>
                            {/if}
                            {#if prop.has_recent_changes}
                                <p class="text-amber-600 text-xs">Updated {timeAgo(prop.last_change_at)}</p>
                            {/if}
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
                            <th class="text-left px-4 py-2 font-medium">Checked</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each filtered as prop (prop.id)}
                            <tr class="border-b hover:bg-gray-50 {prop.has_recent_changes ? 'bg-amber-50' : ''}">
                                <td class="px-4 py-2">
                                    <a href="/property/{prop.id}" class="text-blue-600 hover:underline">{prop.address}</a>
                                </td>
                                <td class="px-4 py-2 text-gray-600">{prop.details || '-'}</td>
                                <td class="px-4 py-2 text-gray-600">{prop.area || '-'}</td>
                                <td class="px-4 py-2">{prop.advertised_price || '-'}</td>
                                <td class="px-4 py-2 text-green-700">{prop.sold_price || '-'}</td>
                                <td class="px-4 py-2 text-gray-400 text-xs">{timeAgo(prop.last_checked)}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    </main>
</div>
