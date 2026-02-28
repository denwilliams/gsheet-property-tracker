<script lang="ts">
    import type { ActionData } from './$types';
    let { form }: { form: ActionData } = $props();
</script>

<div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="w-full max-w-sm">
        <h1 class="text-2xl font-bold text-center mb-8">Property Tracker</h1>

        {#if form?.error}
            <div class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-4">
                {form.error}
            </div>
        {/if}

        <form method="POST" class="bg-white shadow rounded-lg p-6 space-y-4">
            <div>
                <label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                    type="email" name="email" id="email" required
                    value={form?.email ?? ''}
                    class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>
            <div>
                <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                    type="password" name="password" id="password" required
                    class="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>
            <button
                type="submit"
                class="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition-colors"
            >
                Sign in
            </button>
        </form>
    </div>
</div>
