
/* This Source Code Form is subject to the terms of the Mozilla Public
   License, v. 2.0. If a copy of the MPL was not distributed with this
   file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package org.mozilla.fenix.library.history

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.CompoundButton
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import io.reactivex.Observable
import io.reactivex.Observer
import io.reactivex.functions.Consumer
import org.mozilla.fenix.R
import org.mozilla.fenix.mvi.UIView

class HistoryUIView(
    container: ViewGroup,
    actionEmitter: Observer<HistoryAction>,
    changesObservable: Observable<HistoryChange>
) :
    UIView<HistoryState, HistoryAction, HistoryChange>(container, actionEmitter, changesObservable) {

    override val view: RecyclerView = LayoutInflater.from(container.context)
        .inflate(R.layout.component_history, container, true)
        .findViewById(R.id.history_list)

    init {
        view.apply {
            adapter = HistoryAdapter(actionEmitter)
            layoutManager = LinearLayoutManager(container.context)
        }
    }

    override fun updateView() = Consumer<HistoryState> {
        (view.adapter as HistoryAdapter).updateData(it.items, it.mode)
    }
}

private class HistoryAdapter(
    private val actionEmitter: Observer<HistoryAction>
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {
    class HistoryListItemViewHolder(
        view: View,
        private val actionEmitter: Observer<HistoryAction>
    ) : RecyclerView.ViewHolder(view) {

        private val checkbox = view.findViewById<CheckBox>(R.id.should_remove_checkbox)
        private val favicon = view.findViewById<ImageView>(R.id.history_favicon)
        private val title = view.findViewById<TextView>(R.id.history_title)
        private val url = view.findViewById<TextView>(R.id.history_url)
        private var item: HistoryItem? = null
        private var mode: HistoryState.Mode = HistoryState.Mode.Normal
        private val checkListener = object : CompoundButton.OnCheckedChangeListener {
            override fun onCheckedChanged(buttonView: CompoundButton?, isChecked: Boolean) {
                if (mode is HistoryState.Mode.Normal) { return }

                item?.apply {
                    val action = if (isChecked) {
                        HistoryAction.AddItemForRemoval(this)
                    } else {
                        HistoryAction.RemoveItemForRemoval(this)
                    }

                    actionEmitter.onNext(action)
                }
            }
        }

        init {
            view.setOnClickListener {
                if (mode is HistoryState.Mode.Editing) {
                    checkbox.isChecked = !checkbox.isChecked
                    return@setOnClickListener
                }

                item?.apply {
                    actionEmitter.onNext(HistoryAction.Select(this))
                }
            }

            view.setOnLongClickListener {
                item?.apply {
                    actionEmitter.onNext(HistoryAction.EnterEditMode(this))
                }

                true
            }

            checkbox.setOnCheckedChangeListener(checkListener)
        }

        fun bind(item: HistoryItem, mode: HistoryState.Mode) {
            this.item = item
            this.mode = mode

            title.text = item.title
            url.text = item.url

            val isEditing = mode is HistoryState.Mode.Editing
            checkbox.visibility = if (isEditing) { View.VISIBLE } else { View.GONE }
            favicon.visibility = if (isEditing) { View.INVISIBLE } else { View.VISIBLE }

            if (mode is HistoryState.Mode.Editing) {
                checkbox.setOnCheckedChangeListener(null)

                // Don't set the checkbox if it already contains the right value.
                // This prevent us from cutting off the animation
                val shouldCheck = mode.selectedItems.contains(item)
                if (checkbox.isChecked != shouldCheck) {
                    checkbox.isChecked = mode.selectedItems.contains(item)
                }
                checkbox.setOnCheckedChangeListener(checkListener)
            }
        }

        companion object {
            const val LAYOUT_ID = R.layout.history_list_item
        }
    }

    class HistoryHeaderViewHolder(
        view: View
    ) : RecyclerView.ViewHolder(view) {
        private val title = view.findViewById<TextView>(R.id.history_header_title)

        fun bind(title: String) {
            this.title.text = title
        }

        companion object {
            const val LAYOUT_ID = R.layout.history_header
        }
    }

    private var items: List<HistoryItem> = emptyList()
    private var mode: HistoryState.Mode = HistoryState.Mode.Normal

    fun updateData(items: List<HistoryItem>, mode: HistoryState.Mode) {
        this.items = items
        this.mode = mode
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        val view = LayoutInflater.from(parent.context).inflate(viewType, parent, false)

        return when (viewType) {
            HistoryHeaderViewHolder.LAYOUT_ID -> HistoryHeaderViewHolder(view)
            HistoryListItemViewHolder.LAYOUT_ID -> HistoryListItemViewHolder(view, actionEmitter)
            else -> throw IllegalStateException("viewType $viewType does not match to a ViewHolder")
        }
    }

    override fun getItemViewType(position: Int): Int {
        return when (position) {
            0 -> HistoryHeaderViewHolder.LAYOUT_ID
            else -> HistoryListItemViewHolder.LAYOUT_ID
        }
    }

    override fun getItemCount(): Int = items.count() + NUMBER_OF_SECTIONS

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {

        when (holder) {
            is HistoryHeaderViewHolder -> holder.bind("Today")
            is HistoryListItemViewHolder -> holder.bind(items[position - NUMBER_OF_SECTIONS], mode)
        }
    }

    companion object {
        private const val NUMBER_OF_SECTIONS = 1
    }
}