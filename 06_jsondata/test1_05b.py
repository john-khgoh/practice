#Multivariate with tf.keras.utils.timeseries_dataset_from_array()

from os import listdir,getcwd
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow.keras import Input, Model
from sklearn.preprocessing import MinMaxScaler

wd = getcwd()
time = []

#Lists for LAX
lax_time = []
lax_delayed = []
lax_cancelled = []
lax_on_time = []
lax_diverted = []
lax_total = []

#List for SFO
sfo_time = []
sfo_delayed = []
sfo_cancelled = []
sfo_on_time = []
sfo_diverted = []
sfo_total = []

with open('airlines.json') as file:
    file_content = file.read()
    
parsed_json = json.loads(file_content)

#Only print out data for LAX and SFO
for i in parsed_json:  
    if(i['Airport']['Code']=='LAX'):
        lax_time.append(i['Time']['Label'])
        lax_delayed.append(i['Statistics']['Flights']['Delayed'])
        lax_cancelled.append(i['Statistics']['Flights']['Cancelled'])
        lax_on_time.append(i['Statistics']['Flights']['On Time'])
        lax_diverted.append(i['Statistics']['Flights']['Diverted'])
        lax_total.append(i['Statistics']['Flights']['Total'])
    elif(i['Airport']['Code']=='SFO'):
        sfo_time.append(i['Time']['Label'])
        sfo_delayed.append(i['Statistics']['Flights']['Delayed'])
        sfo_cancelled.append(i['Statistics']['Flights']['Cancelled'])
        sfo_on_time.append(i['Statistics']['Flights']['On Time'])
        sfo_diverted.append(i['Statistics']['Flights']['Diverted'])
        sfo_total.append(i['Statistics']['Flights']['Total'])

lax_df = pd.DataFrame({'LAX_Delayed':lax_delayed,'LAX_Cancelled':lax_cancelled,'LAX_Ontime':lax_on_time,'LAX_Diverted':lax_diverted,'LAX_Total':lax_total})
sfo_df = pd.DataFrame({'SFO_Delayed':sfo_delayed,'SFO_Cancelled':sfo_cancelled,'SFO_Ontime':sfo_on_time,'SFO_Diverted':sfo_diverted,'SFO_Total':sfo_total})
time = np.arange(len(lax_df),dtype="int32")

def plot_series(time, series, format="-", start=0, end=None):
    plt.plot(time[start:end], series[start:end], format)
    plt.xlabel("Time")
    plt.ylabel("Value")
    plt.grid(False)

#Hyperparameters
split_time_ratio = 0.80 #The ratio between training and validation data
split_time = int(split_time_ratio * len(time)) #The cutoff point between training and validation data
shuffle_buffer = 128 #Doesn't seem very important. Just ensure it's a large number. 
batch_size = 64 #Just the ordinary neural network batch size i.e. how many training examples to train at once 
window_size = 6 #Window size should approximate the periodicity of the waveform e.g. if it repeats every 7 days, the window should be 7
epochs = 40
learning_rate = 0.02

conv_layer_filters = 32
lstm_layer = 12
dense_layer = [24,12,1]

#Keep the columns of interest
series = lax_df[['LAX_Delayed','LAX_Cancelled','LAX_Ontime','LAX_Total']]
series_valid_copy = series[split_time:]
no_of_cols = series.shape[1]

#Store the means and standard deviations for denormalization
list_of_means = list(series.mean())
list_of_sds = list(series.std())

#Normalization of the dataframe
#series = series.apply(lambda x:abs(x-x.mean())/x.std())
#minmaxscaler = MinMaxScaler(feature_range=(0,1))
#original_dim_y = np.shape(series)[1] #Get the no. of columns from series for inverse_transformation_later
#series = minmaxscaler.fit_transform(series)

#Normalization of the dataframe
series = series.apply(lambda x:abs(x-x.mean())/x.std())

time_train = time[:split_time]
time_valid = time[split_time:]
series_train = series[:split_time]
series_valid = series[split_time:]

train_ds = tf.keras.utils.timeseries_dataset_from_array(
    series_train,
    targets = series_train['LAX_Delayed'],
    sequence_length = window_size,
    batch_size = batch_size,
    shuffle = True
)
valid_ds = tf.keras.utils.timeseries_dataset_from_array(
    series_valid,
    targets = series_valid['LAX_Delayed'],
    sequence_length = window_size,
    batch_size = batch_size,
    shuffle = True
)

'''
#Windowing of the dataset
def window(series,window_size,shuffle_buffer,batch_size):
    dataset = tf.data.Dataset.from_tensor_slices(series)
    dataset = dataset.window(window_size + 1, shift=1, drop_remainder=True) #Creates windows of 'window_size' where elements of each window shifts by the 'shift' argument
    dataset = dataset.flat_map(lambda w: w.batch(window_size + 1)) #Group the windows into a single dataset
    dataset = dataset.shuffle(shuffle_buffer) #Randomly shuffle the above dataset
    dataset = dataset.map(lambda window: (window[:-1], window[-1])) #For each window split the elements into tuples: (i) every element before the last (ii) the last element
    dataset = dataset.batch(batch_size).prefetch(1) #Turn the dataset of tuples into batches
    return dataset
   
dataset = window(series_train,window_size,shuffle_buffer,batch_size)
''' 
model = tf.keras.models.Sequential([ 
        tf.keras.layers.Conv1D(filters=conv_layer_filters,kernel_size=5,strides=1,activation='relu',input_shape=[None,no_of_cols]),
        tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(lstm_layer,return_sequences=True)),
        tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(lstm_layer)),
        tf.keras.layers.Dense(dense_layer[0],activation='relu'),
        tf.keras.layers.Dense(dense_layer[1],activation='relu'),
        tf.keras.layers.Dense(dense_layer[2],activation='relu')
    ])
   
model.compile(loss=tf.keras.losses.Huber(),
                  optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
                  metrics=["mae"])  
             
history = model.fit(train_ds,epochs=epochs)

def model_forecast(model, series, window_size):
    ds = tf.data.Dataset.from_tensor_slices(series)
    ds = ds.window(window_size, shift=1, drop_remainder=True)
    ds = ds.flat_map(lambda w: w.batch(window_size))
    ds = ds.batch(batch_size).prefetch(1)
    forecast = model.predict(ds)
    return forecast
   
forecast_series = series[split_time - window_size:-1]
rnn_forecast = model_forecast(model, forecast_series, window_size).squeeze()

#Denormalize function is problematic. It creates a Dataframe containing lists. 
def denormalize(df,list_of_means,list_of_sds):
    df_cols = df.columns
    for i,j in enumerate(df_cols):
        df[j] = df[j].apply(lambda x:int(x * list_of_sds[i]) + list_of_means[i])
    return df
    
def rescale(series,mean,std):
    series = (series * std) + mean
    return series

#rnn_forecast_df = pd.DataFrame(rnn_forecast)
#rnn_forecast_df.columns = ['LAX_Delayed_prediction']
#rnn_forecast_df = denormalize(rnn_forecast_df,list_of_means,list_of_sds)
rnn_forecast_df = rescale(rnn_forecast,list_of_means[0],list_of_sds[0])

naive_forecast = np.array([list_of_means[0]] * len(rnn_forecast))

mae_naive = tf.keras.metrics.mean_absolute_error(series_valid_copy['LAX_Delayed'],naive_forecast).numpy()
mae_rnn = tf.keras.metrics.mean_absolute_error(series_valid_copy['LAX_Delayed'],rnn_forecast_df).numpy()
print(mae_naive,mae_rnn)

plt.figure(figsize=(10, 6))
plot_series(time_valid, series_valid_copy['LAX_Delayed'])
plot_series(time_valid, rnn_forecast_df)
plt.show()