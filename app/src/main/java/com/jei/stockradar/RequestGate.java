package com.jei.stockradar;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executor;

/** Suppress duplicate refreshes while queued or running, without caching data. */
final class RequestGate {
    private final Map<String, Object> pending = new HashMap<>();

    void execute(Executor executor, String key, Runnable task) {
        final Object request = new Object();
        synchronized (pending) {
            if (pending.containsKey(key)) return;
            pending.put(key, request);
        }
        try {
            executor.execute(() -> {
                try {
                    task.run();
                } finally {
                    release(key, request);
                }
            });
        } catch (RuntimeException | Error failure) {
            release(key, request);
            throw failure;
        }
    }

    private void release(String key, Object request) {
        synchronized (pending) {
            if (pending.get(key) == request) pending.remove(key);
        }
    }
}
