<script lang="ts">
    import type { PageData } from './$types';

    let { data }: { data: PageData } = $props();
    const { property, changes, snapshots } = data;

    function formatDate(dateStr: string): string {
        return new Date(dateStr).toLocaleDateString('en-AU', {
            day: 'numeric', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    }

    function urlDomain(url: string): string {
        try {
            return new URL(url).hostname.replace('www.', '');
        } catch {
            return url;
        }
    }
</script>

<div class="min-h-screen bg-gray-50">
    <header class="bg-white shadow-sm border-b">
        <div class="max-w-4xl mx-auto px-4 py-4">
            <a href="/" class="text-sm text-blue-600 hover:underline mb-2 inline-block">&larr; Back</a>
            <h1 class="text-xl font-bold">{property.address}</h1>
        </div>
    </header>

    <main class="max-w-4xl mx-auto px-4 py-6 space-y-6">
        <div class="bg-white rounded-lg shadow-sm border p-6">
            <div class="grid grid-cols-2 gap-4 text-sm">
                {#if property.details}
                    <div>
                        <span class="text-gray-500">Details</span>
                        <p class="font-medium">{property.details}</p>
                    </div>
                {/if}
                {#if property.area}
                    <div>
                        <span class="text-gray-500">Area</span>
                        <p class="font-medium">{property.area}</p>
                    </div>
                {/if}
                {#if property.advertised_price}
                    <div>
                        <span class="text-gray-500">Advertised Price</span>
                        <p class="font-medium">{property.advertised_price}</p>
                    </div>
                {/if}
                {#if property.sold_price}
                    <div>
                        <span class="text-gray-500">Sold Price</span>
                        <p class="font-medium text-green-700">{property.sold_price}</p>
                    </div>
                {/if}
                {#if property.sold_date}
                    <div>
                        <span class="text-gray-500">Sold Date</span>
                        <p class="font-medium">{property.sold_date}</p>
                    </div>
                {/if}
            </div>

            {#if property.notes}
                <div class="mt-4 pt-4 border-t">
                    <span class="text-sm text-gray-500">Notes</span>
                    <p class="text-sm mt-1">{property.notes}</p>
                </div>
            {/if}

            <div class="mt-4 pt-4 border-t flex gap-3">
                {#if property.url}
                    <a href={property.url} target="_blank" rel="noopener"
                       class="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
                        {urlDomain(property.url)} &#8599;
                    </a>
                {/if}
                {#if property.url2}
                    <a href={property.url2} target="_blank" rel="noopener"
                       class="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
                        {urlDomain(property.url2)} &#8599;
                    </a>
                {/if}
            </div>

            {#if property.last_checked}
                <p class="text-xs text-gray-400 mt-3">Last checked: {formatDate(property.last_checked)}</p>
            {/if}
        </div>

        {#if snapshots.length > 0}
            <div class="bg-white rounded-lg shadow-sm border p-6">
                <h2 class="font-semibold mb-4">Current Listing Data</h2>
                <div class="space-y-4">
                    {#each snapshots as snap}
                        <div class="border rounded p-4 text-sm">
                            <div class="flex items-center justify-between mb-2">
                                <span class="font-medium">{urlDomain(snap.url)}</span>
                                {#if snap.fetch_error}
                                    <span class="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">Error</span>
                                {:else}
                                    <span class="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">{snap.status || 'OK'}</span>
                                {/if}
                            </div>
                            {#if snap.fetch_error}
                                <p class="text-red-600 text-xs">{snap.fetch_error}</p>
                            {:else}
                                <div class="grid grid-cols-2 gap-2 text-xs text-gray-600">
                                    {#if snap.price}<p>Price: {snap.price}</p>{/if}
                                    {#if snap.bedrooms != null}<p>Beds: {snap.bedrooms} / Bath: {snap.bathrooms} / Car: {snap.parking}</p>{/if}
                                    {#if snap.agent_name}<p>Agent: {snap.agent_name} ({snap.agency_name})</p>{/if}
                                    {#if snap.auction_date}<p>Auction: {formatDate(snap.auction_date)}</p>{/if}
                                    {#if snap.photo_count}<p>Photos: {snap.photo_count}</p>{/if}
                                </div>
                            {/if}
                            <p class="text-xs text-gray-400 mt-2">Fetched: {formatDate(snap.fetched_at)}</p>
                        </div>
                    {/each}
                </div>
            </div>
        {/if}

        <div class="bg-white rounded-lg shadow-sm border p-6">
            <h2 class="font-semibold mb-4">Change History</h2>
            {#if changes.length === 0}
                <p class="text-sm text-gray-500">No changes detected yet.</p>
            {:else}
                <div class="space-y-3">
                    {#each changes as change}
                        <div class="border-l-2 border-gray-200 pl-4 py-1">
                            <p class="text-xs text-gray-400">{formatDate(change.detected_at)}</p>
                            <p class="text-sm">
                                <span class="font-medium">{change.field}</span>:
                                <span class="text-red-600 line-through">{change.old_value || '(empty)'}</span>
                                &rarr;
                                <span class="text-green-700">{change.new_value || '(empty)'}</span>
                            </p>
                            <p class="text-xs text-gray-400">{urlDomain(change.url)}</p>
                        </div>
                    {/each}
                </div>
            {/if}
        </div>
    </main>
</div>
